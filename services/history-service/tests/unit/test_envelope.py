from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from history_service.schemas.envelope import EventEnvelope


def _base(**overrides):
    data = {
        "game_id": "g1",
        "actor": "agent",
        "event_type": "move",
        "payload": {"intended_action": "play"},
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": "g1:agent:0",
        "producer_offset": 0,
    }
    data.update(overrides)
    return data


def test_accepts_well_formed_envelope():
    env = EventEnvelope.model_validate(_base())
    assert env.envelope_version == 1
    assert env.actor == "agent"
    assert env.event_id  # auto-generated uuid when omitted


def test_accepts_game_service_actor():
    env = EventEnvelope.model_validate(_base(actor="game-service"))
    assert env.actor == "game-service"


def test_accepts_evaluator_actor():
    env = EventEnvelope.model_validate(_base(actor="evaluator"))
    assert env.actor == "evaluator"


def test_accepts_user_prompt_event():
    env = EventEnvelope.model_validate(
        _base(actor="user", event_type="user_prompt", payload={"prompt": "play a card"})
    )
    assert env.actor == "user"
    assert env.event_type == "user_prompt"
    assert env.payload == {"prompt": "play a card"}


def test_rejects_missing_game_id():
    data = _base()
    del data["game_id"]
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_rejects_missing_actor():
    data = _base()
    del data["actor"]
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_rejects_missing_event_type():
    data = _base()
    del data["event_type"]
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(data)


def test_rejects_unknown_actor():
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(_base(actor="referee"))


def test_tolerates_unknown_forward_compatible_fields():
    env = EventEnvelope.model_validate(_base(some_future_field={"x": 1}, extra="ok"))
    assert env.game_id == "g1"


def test_accepts_evaluation_event_with_player_in_payload():
    # A per-player evaluation verdict carries an optional ``player`` key in its
    # payload; the envelope accepts it (payload is an open dict).
    env = EventEnvelope.model_validate(
        _base(
            actor="evaluator",
            event_type="evaluation",
            payload={
                "scope": "round",
                "target_seq": 4,
                "player": "player1",
                "overall_score": 7,
            },
        )
    )
    assert env.payload["player"] == "player1"
    assert env.payload["scope"] == "round"


def test_accepts_evaluation_event_without_player():
    # Backward compatible: an evaluation event predating per-player scoring has
    # no ``player`` and is still accepted.
    env = EventEnvelope.model_validate(
        _base(
            actor="evaluator",
            event_type="evaluation",
            payload={"scope": "move", "target_seq": 2, "overall_score": 5},
        )
    )
    assert "player" not in env.payload


def test_producer_offset_accepts_str_or_int():
    assert (
        EventEnvelope.model_validate(_base(producer_offset="abc-1")).producer_offset
        == "abc-1"
    )
    assert EventEnvelope.model_validate(_base(producer_offset=5)).producer_offset == 5
