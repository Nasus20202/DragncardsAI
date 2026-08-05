"""Reading an event's orchestration mode back out of the store.

The payload is stored verbatim, so the mode is whatever the producer wrote — and
the producer omits the key entirely for chat mode. That makes the read side, not
the write side, responsible for resolving the default, and it makes the default a
single-source-of-truth question: :func:`session_mode_of` is the only place that
knows an absent key means ``chat``, and :class:`EventResponse` is the only place
that projects it for a reader.

The requirement this covers has one edge that is easy to get wrong: the mode must
be readable WITHOUT inferring it from the presence of a seat identifier. An
orchestrated event with no ``player`` is the coordinating agent's own bookkeeping,
and reading a missing seat as evidence of chat mode would misclassify exactly
those events.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from history_service.schemas.api import EventResponse
from history_service.schemas.envelope import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
    StoredEvent,
    session_mode_of,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _stored(**payload) -> StoredEvent:
    return StoredEvent(
        event_id="evt-1",
        game_id="g1",
        seq=1,
        envelope_version=1,
        actor="agent",
        event_type="agent_move",
        payload=payload,
        occurred_at=NOW,
        recorded_at=NOW,
        idempotency_key="g1:agent:1",
        producer_offset=1,
    )


# --- the helper --------------------------------------------------------------


def test_an_event_predating_the_mode_reads_as_chat():
    assert session_mode_of({"intended_action": "play"}) == SESSION_MODE_CHAT


def test_an_empty_payload_reads_as_chat():
    assert session_mode_of({}) == SESSION_MODE_CHAT


def test_an_orchestrated_event_reads_as_orchestrated():
    payload = {"intended_action": "play", "session_mode": "orchestrated"}

    assert session_mode_of(payload) == SESSION_MODE_ORCHESTRATED


@pytest.mark.parametrize("value", ["swarm", "Orchestrated", "", None, 7, ["chat"]])
def test_an_unknown_mode_value_reads_as_chat(value):
    """A mode this service does not know is not one it can project honestly."""
    assert session_mode_of({"session_mode": value}) == SESSION_MODE_CHAT


def test_the_mode_is_not_inferred_from_a_seat_identifier():
    seatless_orchestrated = {"intended_action": "villain_encounter_phase"}
    seatless_orchestrated["session_mode"] = SESSION_MODE_ORCHESTRATED

    # No seat, still orchestrated: the coordinating agent's own bookkeeping.
    assert "player" not in seatless_orchestrated
    assert session_mode_of(seatless_orchestrated) == SESSION_MODE_ORCHESTRATED

    # And a seat on a chat-mode payload does not make it orchestrated.
    assert session_mode_of({"player": "player1"}) == SESSION_MODE_CHAT


# --- the reader projection --------------------------------------------------


def test_the_event_response_projects_chat_for_a_payload_without_the_key():
    response = EventResponse.from_stored(_stored(intended_action="play"))

    assert response.session_mode == SESSION_MODE_CHAT


def test_the_event_response_projects_the_orchestrated_mode_and_the_seat():
    response = EventResponse.from_stored(
        _stored(
            intended_action="play",
            session_mode=SESSION_MODE_ORCHESTRATED,
            player="player2",
        )
    )

    assert response.session_mode == SESSION_MODE_ORCHESTRATED
    assert response.payload["player"] == "player2"


def test_the_orchestrators_own_event_projects_the_mode_with_no_seat():
    response = EventResponse.from_stored(
        _stored(
            intended_action="villain_encounter_phase",
            session_mode=SESSION_MODE_ORCHESTRATED,
        )
    )

    assert response.session_mode == SESSION_MODE_ORCHESTRATED
    assert "player" not in response.payload


def test_the_payload_is_still_returned_verbatim():
    """Projecting the mode must not consume, rewrite or move the stored key."""
    stored = _stored(
        intended_action="play", session_mode=SESSION_MODE_ORCHESTRATED, reasoning="r"
    )

    response = EventResponse.from_stored(stored)

    assert response.payload == stored.payload
