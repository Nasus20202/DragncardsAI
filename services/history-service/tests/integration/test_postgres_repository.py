from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from history_service.runtime.transfer import BundleReader, iter_export_lines
from history_service.schemas.envelope import EventEnvelope
from history_service.storage.repository import GameHistoryExistsError


def _envelope(game_id: str, *, actor="game-service", offset=0, event_type="state"):
    return EventEnvelope(
        game_id=game_id,
        actor=actor,
        event_type=event_type,
        payload={"offset": offset},
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:{actor}:{offset}",
        producer_offset=offset,
    )


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_gap_free_seq_on_postgres(postgres_repository):
    for offset in range(5):
        result = await postgres_repository.commit_event(_envelope("g1", offset=offset))
        assert result.event.seq == offset + 1
    events = await postgres_repository.list_events("g1")
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_duplicate_stored_once_on_postgres(postgres_repository):
    first = await postgres_repository.commit_event(_envelope("g1", offset=0))
    dup = await postgres_repository.commit_event(_envelope("g1", offset=0))
    assert first.inserted and not dup.inserted
    assert dup.event.seq == 1
    assert len(await postgres_repository.list_events("g1")) == 1


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_concurrent_commits_preserve_gap_free_seq(postgres_repository):
    """Two concurrent ingesters committing the same game keep one gap-free series.

    The per-game advisory lock serializes seq assignment; the unique constraint
    collapses duplicates. After the storm, seqs are exactly 1..N with no gaps.
    """
    envelopes = [_envelope("g1", offset=i) for i in range(20)]
    # Submit each envelope twice concurrently (at-least-once duplicates).
    tasks = [
        postgres_repository.commit_event(env) for env in envelopes for _ in range(2)
    ]
    await asyncio.gather(*tasks)
    events = await postgres_repository.list_events("g1", limit=1000)
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, 21))  # gap-free, each offset stored once


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_list_games_grouped_on_postgres(postgres_repository):
    await postgres_repository.commit_event(_envelope("g1", offset=0))
    await postgres_repository.commit_event(_envelope("g1", offset=1))
    await postgres_repository.commit_event(_envelope("g2", offset=0))

    games = await postgres_repository.list_games()
    # Ordered by last_recorded_at DESC: g2 recorded after g1.
    assert [summary.game_id for summary in games] == ["g2", "g1"]
    by_id = {summary.game_id: summary for summary in games}
    assert by_id["g1"].event_count == 2
    assert by_id["g2"].event_count == 1
    assert by_id["g1"].first_recorded_at <= by_id["g1"].last_recorded_at


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_delete_game_history_on_postgres(postgres_repository):
    for offset in range(3):
        await postgres_repository.commit_event(_envelope("g1", offset=offset))
    await postgres_repository.write_snapshot("g1", 2, {"schema_version": 1, "game": {}})
    await postgres_repository.commit_event(_envelope("g2", offset=0))

    result = await postgres_repository.delete_game_history("g1")
    assert result.deleted_events == 3
    assert result.deleted_snapshots == 1
    assert await postgres_repository.list_events("g1") == []
    assert await postgres_repository.list_snapshots("g1") == []
    # The untouched game survives.
    assert {s.game_id for s in await postgres_repository.list_games()} == {"g2"}

    # Idempotent: deleting again removes nothing.
    again = await postgres_repository.delete_game_history("g1")
    assert again.deleted_events == 0
    assert again.deleted_snapshots == 0


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_timeline_summary_prunes_jsonb_on_postgres(postgres_repository):
    """The Postgres pruning path is dialect-specific, so it needs a real Postgres.

    Unit tests exercise the sqlite ``json_remove`` branch; this covers the
    ``jsonb - 'key'`` branch and the ``#>>`` text reads of the round and step,
    including that a dotted step id survives as a string and round 0 as 0.
    """
    payload = {
        "state": {
            "deltas": [{"i": i} for i in range(20)],
            "game": {
                "roundNumber": 0,
                "stepId": "0.1",
                "mode": "in progress",
                "cardById": {f"card-{i}": {"text": "x" * 200} for i in range(50)},
            },
        },
        "status": "in progress",
        "action_args": {"type": "next_step"},
    }
    envelope = EventEnvelope(
        game_id="g1",
        actor="game-service",
        event_type="game_state",
        payload=payload,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key="g1:game-service:0",
        producer_offset=0,
    )
    await postgres_repository.commit_event(envelope)
    await postgres_repository.commit_event(
        EventEnvelope(
            game_id="g1",
            actor="agent",
            event_type="agent_decision",
            payload={
                "intended_action": "move_card",
                "conversation_context": [{"role": "user", "content": "x" * 5000}],
            },
            occurred_at=datetime.now(timezone.utc),
            idempotency_key="g1:agent:0",
            producer_offset=1,
        )
    )

    state_entry, agent_entry = await postgres_repository.list_event_summaries("g1")

    assert state_entry.payload["state"] == {"game": {"roundNumber": 0, "stepId": "0.1"}}
    assert state_entry.payload["status"] == "in progress"
    assert state_entry.payload["action_args"] == {"type": "next_step"}
    assert "conversation_context" not in agent_entry.payload
    assert agent_entry.payload["intended_action"] == "move_card"
    assert "state" not in agent_entry.payload

    # The full payload is still intact on the events read.
    full_state, _ = await postgres_repository.list_events("g1")
    assert len(full_state.payload["state"]["game"]["cardById"]) == 50


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_timeline_summary_paging_on_postgres(postgres_repository):
    for offset in range(5):
        await postgres_repository.commit_event(_envelope("g1", offset=offset))
    page1 = await postgres_repository.list_event_summaries("g1", after_seq=0, limit=2)
    assert [e.seq for e in page1] == [1, 2]
    page2 = await postgres_repository.list_event_summaries("g1", after_seq=2, limit=2)
    assert [e.seq for e in page2] == [3, 4]
    assert page2[0].payload == {"offset": 2}


# -- bundle round trip on Postgres ------------------------------------------

_PLUGIN_STATICS = {
    "functions": {f"fn{n}": ["ACTION", f"body-{n}"] for n in range(12)},
    "layout": [[f"cell-{n}" for n in range(12)]],
}
_CONVERSATION = [
    {"role": "system", "content": "you play Marvel Champions. " * 12},
    {"role": "user", "content": "take your turn. " * 12},
]


def _state_envelope(game_id: str, offset: int) -> EventEnvelope:
    return EventEnvelope(
        game_id=game_id,
        actor="game-service",
        event_type="game_state",
        payload={
            "plugin_name": "marvel-champions",
            "action_path": "actions",
            "action_args": {"type": "move_card", "instance_id": f"c{offset}"},
            # A payload object whose only key is a marker: the escape has to
            # survive JSONB, not only the codec.
            "marker": {"$ref": "not-a-reference"},
            "state": {
                "game": {"lastCard": f"c{offset}", **_PLUGIN_STATICS},
                "deltas": [{"step": s, "pad": "d" * 300} for s in range(offset + 1)],
            },
        },
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:game-service:{offset}",
        producer_offset=offset,
    )


def _agent_envelope(game_id: str, offset: int) -> EventEnvelope:
    return EventEnvelope(
        game_id=game_id,
        actor="agent",
        event_type="agent_move",
        payload={
            "intended_action": "move_card",
            "reasoning": "ラウンド 3 — Rhino attaque " * 8,
            "arguments": {"instance_id": "c1", "session_id": game_id},
            "conversation_context": _CONVERSATION,
        },
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:agent:{offset}",
        producer_offset=offset,
    )


async def _seed_bundle_game(repository, game_id: str, *, events: int = 8) -> None:
    for offset in range(events):
        envelope = (
            _agent_envelope(game_id, offset)
            if offset % 2
            else _state_envelope(game_id, offset)
        )
        await repository.commit_event(envelope)
    await repository.write_snapshot(
        game_id, 4, {"plugin_name": "marvel-champions", "game": _PLUGIN_STATICS}
    )


async def _export(repository, game_id: str, mode: str = "full") -> bytes:
    return "".join(
        [line async for line in iter_export_lines(repository, game_id, mode=mode)]
    ).encode()


async def _import(repository, bundle: bytes, target: str):
    async def chunks():
        yield bundle

    reader = BundleReader(chunks(), max_bytes=64 * 1024 * 1024)
    await reader.read_header()
    result = await repository.import_game_history(target, reader.records())
    return result, reader


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_bundle_round_trip_preserves_every_stored_field_on_postgres(
    postgres_repository,
):
    """The store, not just the codec: JSONB is what the payloads land in."""
    await _seed_bundle_game(postgres_repository, "g1", events=8)
    bundle = await _export(postgres_repository, "g1")

    result, reader = await _import(postgres_repository, bundle, "g1copy")
    assert result.imported_events == 8
    assert result.imported_snapshots == 1
    # Every agent move records the source id in `arguments.session_id`.
    assert reader.source_id_references == 4

    original = await postgres_repository.list_events("g1", limit=100)
    copy = await postgres_repository.list_events("g1copy", limit=100)
    assert len(copy) == len(original) == 8
    for before, after in zip(original, copy):
        assert after.seq == before.seq
        assert after.event_id == before.event_id
        assert after.envelope_version == before.envelope_version
        assert after.actor == before.actor
        assert after.event_type == before.event_type
        assert after.payload == before.payload
        assert after.occurred_at == before.occurred_at
        assert after.recorded_at == before.recorded_at
        assert after.idempotency_key == before.idempotency_key
        assert after.producer_offset == before.producer_offset
    # The escape survived a trip through JSONB in both directions.
    assert copy[0].payload["marker"] == {"$ref": "not-a-reference"}

    original_snaps = await postgres_repository.list_snapshots("g1")
    copy_snaps = await postgres_repository.list_snapshots("g1copy")
    for before, after in zip(original_snaps, copy_snaps):
        assert after.snapshot_at_seq == before.snapshot_at_seq
        assert after.snapshot == before.snapshot
        assert after.created_at == before.created_at

    # Re-exporting the copy reproduces the bundle, header aside.
    again = await _export(postgres_repository, "g1copy")
    before_lines = [json.loads(line) for line in bundle.decode().splitlines()]
    after_lines = [json.loads(line) for line in again.decode().splitlines()]
    for record in (before_lines[0], after_lines[0]):
        record.pop("exported_at")
        record.pop("game_id")
    assert before_lines == after_lines


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_importing_the_same_bundle_twice_never_collides_on_postgres(
    postgres_repository,
):
    """The 409 is one target id, not a globally unique row in the store."""
    await _seed_bundle_game(postgres_repository, "g1", events=4)
    bundle = await _export(postgres_repository, "g1")

    first, _ = await _import(postgres_repository, bundle, str(uuid4()))
    second, _ = await _import(postgres_repository, bundle, str(uuid4()))
    assert first.game_id != second.game_id
    assert first.imported_events == second.imported_events == 4

    with pytest.raises(GameHistoryExistsError):
        await _import(postgres_repository, bundle, "g1")
    # The refused import left the source untouched.
    assert len(await postgres_repository.list_events("g1", limit=100)) == 4


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_a_minimal_bundle_loses_exactly_the_conversation_on_postgres(
    postgres_repository,
):
    await _seed_bundle_game(postgres_repository, "g1", events=8)
    bundle = await _export(postgres_repository, "g1", mode="minimal")

    result, _ = await _import(postgres_repository, bundle, "g1min")
    assert result.imported_events == 8

    original = await postgres_repository.list_events("g1", limit=100)
    copy = await postgres_repository.list_events("g1min", limit=100)
    for before, after in zip(original, copy):
        assert after.payload == {
            key: value
            for key, value in before.payload.items()
            if key != "conversation_context"
        }
        assert "conversation_context" not in after.payload
