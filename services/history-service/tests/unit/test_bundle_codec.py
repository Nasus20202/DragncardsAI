from __future__ import annotations

import json
from typing import Any

import pytest

from history_service.runtime.bundle_codec import (
    DEDUP_THRESHOLD_BYTES,
    LITERAL_KEY,
    MAX_NESTING_DEPTH,
    REF_KEY,
    BlobTable,
    BlobTableError,
    BlobTableTooLargeError,
    BlobWriter,
)

BIG = "x" * 400
HUGE_CEILING = 1 << 30


def _big_object(marker: str = "a") -> dict:
    return {"text": BIG, "marker": marker}


def _round_trip(value, *, threshold: int = DEDUP_THRESHOLD_BYTES):
    """Encode one payload and read it back through a fresh blob table."""
    writer = BlobWriter(threshold=threshold)
    encoded, blobs = writer.encode(value, "event[1].payload")
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    for line, blob in enumerate(blobs, start=2):
        table.add(line, blob["id"], blob["value"])
    return table.resolve(99, encoded), encoded, blobs


# -- extraction --------------------------------------------------------------


def test_a_value_repeated_across_records_is_carried_once():
    writer = BlobWriter()
    shared = _big_object()

    first, first_blobs = writer.encode({"state": shared}, "event[1].payload")
    second, second_blobs = writer.encode({"state": shared}, "event[2].payload")

    assert len(first_blobs) == 1
    assert second_blobs == [], "the second record should reference, not re-emit"
    assert first["state"] == second["state"] == {REF_KEY: "b1"}
    assert first_blobs[0]["first_seen"] == "event[1].payload.state"


def test_small_values_stay_inline():
    _, encoded, blobs = _round_trip({"a": 1, "b": "short"})
    assert blobs == []
    assert encoded == {"a": 1, "b": "short"}


def test_a_growing_prefix_list_shares_its_elements():
    """DragnCards' delta log: event *n* re-ships every delta before it."""
    writer = BlobWriter()
    deltas = [_big_object(str(index)) for index in range(4)]

    encodings = []
    total_blobs = 0
    for step in range(1, 5):
        encoded, blobs = writer.encode(
            {"deltas": deltas[:step]}, f"event[{step}].payload"
        )
        total_blobs += len(blobs)
        encodings.append(encoded)

    # Four distinct deltas, carried once each. The lists themselves are short
    # enough to stay inline once their elements are references.
    assert total_blobs == 4
    # The last event's delta log is four references, not four copies.
    assert encodings[-1]["deltas"] == [{REF_KEY: f"b{n}"} for n in range(1, 5)]
    assert encodings[0]["deltas"] == [{REF_KEY: "b1"}]


def test_nested_blobs_are_emitted_before_the_blob_that_references_them():
    writer = BlobWriter()
    encoded, blobs = writer.encode(
        {"outer": {"inner": _big_object(), "also": _big_object("b")}},
        "event[1].payload",
    )
    ids = [blob["id"] for blob in blobs]
    assert ids == sorted(ids, key=lambda value: int(value[1:]))
    # Post-order: both members are emitted before the record that holds them,
    # and the holder is small enough to stay inline as a pair of references.
    # Ids follow the sorted walk, so "also" is encountered before "inner".
    assert encoded["outer"] == {"also": {REF_KEY: "b1"}, "inner": {REF_KEY: "b2"}}


def test_a_record_keeps_its_own_shape_on_its_own_line():
    """The payload itself is never extracted, however big it is.

    Pulling the root out would leave the record's line reading
    ``"payload": {"$ref": "b1"}``, which says nothing about what the record is
    and costs a blob wrapper plus a reference for no saving.
    """
    writer = BlobWriter()
    encoded, blobs = writer.encode(
        {"action": "move_card", "state": _big_object(), "status": "in progress"},
        "event[1].payload",
    )
    assert encoded == {
        "action": "move_card",
        "state": {REF_KEY: "b1"},
        "status": "in progress",
    }
    assert [blob["first_seen"] for blob in blobs] == ["event[1].payload.state"]


def test_a_payload_that_is_itself_a_marker_object_is_escaped_not_extracted():
    payload = {REF_KEY: BIG}
    resolved, encoded, blobs = _round_trip(payload)
    assert resolved == payload
    assert blobs == []
    assert encoded == {LITERAL_KEY: {REF_KEY: BIG}}


def test_encoding_is_deterministic():
    payload = {"a": _big_object(), "b": [_big_object("b"), _big_object()]}
    first = BlobWriter().encode(payload, "event[1].payload")
    second = BlobWriter().encode(payload, "event[1].payload")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# -- escaping ----------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"data": {REF_KEY: "not-a-reference"}},
        {"data": {LITERAL_KEY: "also-real-data"}},
        {"data": {REF_KEY: {LITERAL_KEY: {REF_KEY: 1}}}},
        {"data": {REF_KEY: BIG}},
        {LITERAL_KEY: [{REF_KEY: "x"}, {LITERAL_KEY: {REF_KEY: "y"}}]},
    ],
)
def test_marker_objects_in_real_data_round_trip(payload):
    resolved, encoded, _ = _round_trip(payload)
    assert resolved == payload
    # The escape is what makes this work: the payload's own marker object is
    # never written as a bare reference.
    assert encoded != payload or LITERAL_KEY not in json.dumps(payload)


def test_non_ascii_and_deep_nesting_round_trip():
    payload: dict = {"note": "ラウンド 3 — Rhino attaque", "big": BIG}
    for _ in range(20):
        payload = {"deeper": payload, "pad": BIG}
    resolved, _, _ = _round_trip(payload)
    assert resolved == payload


# -- resolution failures -----------------------------------------------------


def test_an_unknown_reference_is_rejected():
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    with pytest.raises(BlobTableError) as exc:
        table.resolve(7, {"state": {REF_KEY: "b9"}})
    assert "line 7" in str(exc.value)
    assert "b9" in str(exc.value)


def test_a_forward_reference_is_rejected():
    """Blob 1 may not name blob 2, which is defined on a later line."""
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    with pytest.raises(BlobTableError):
        table.add(2, "b1", {"inner": {REF_KEY: "b2"}})


def test_a_duplicate_blob_id_is_rejected():
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    table.add(2, "b1", {"a": 1})
    with pytest.raises(BlobTableError) as exc:
        table.add(3, "b1", {"a": 2})
    assert "duplicate blob id" in str(exc.value)


def test_a_reference_bomb_is_refused_before_it_is_expanded():
    """``b2 = [b1, b1]``, ``b3 = [b2, b2]``, ... doubles at every line."""
    table = BlobTable(max_expanded_bytes=64 * 1024)
    table.add(2, "b1", {"pad": BIG})
    previous = "b1"
    with pytest.raises(BlobTableTooLargeError) as exc:
        for index in range(2, 40):
            blob_id = f"b{index}"
            table.add(index + 1, blob_id, [{REF_KEY: previous}, {REF_KEY: previous}])
            previous = blob_id
    assert "ceiling" in str(exc.value)
    # Refused well before 2**38 copies of a 400-byte string were built.
    assert len(table) < 12


def test_nesting_deeper_than_the_limit_is_refused_rather_than_overflowing():
    """A stranger's file must not decide how deep this process recurses."""
    value: Any = {"leaf": 1}
    for _ in range(MAX_NESTING_DEPTH + 5):
        value = {"d": value}
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    with pytest.raises(BlobTableError) as exc:
        table.expanded_size(9, value)
    assert "line 9" in str(exc.value)
    assert str(MAX_NESTING_DEPTH) in str(exc.value)


def test_the_escape_must_wrap_an_object():
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    with pytest.raises(BlobTableError):
        table.resolve(4, {LITERAL_KEY: "not an object"})


# -- source-id counting ------------------------------------------------------


def test_shared_content_is_scanned_once_for_the_source_id():
    writer = BlobWriter()
    payload = {"conversation": [{"content": f"session game-42 said {BIG}"}]}
    encoded, blobs = writer.encode(payload, "event[1].payload")
    again, no_blobs = writer.encode(payload, "event[2].payload")

    table = BlobTable(max_expanded_bytes=HUGE_CEILING, source_game_id="game-42")
    for line, blob in enumerate(blobs, start=2):
        table.add(line, blob["id"], blob["value"])

    assert no_blobs == []
    assert table.mentions_source(encoded) is True
    # The second record is a bare reference, and still answers correctly.
    assert table.mentions_source(again) is True
    assert table.mentions_source({"unrelated": "text"}) is False


def test_no_source_id_means_nothing_is_counted():
    table = BlobTable(max_expanded_bytes=HUGE_CEILING)
    assert table.mentions_source({"content": "game-42"}) is False
