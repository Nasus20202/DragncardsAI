"""Unit tests for the history ingestion emitter and game-service emission.

These tests prove:
- ``execute_action`` emits exactly one history state event per executed action
  with the session id as ``game_id`` and the resulting status.
- ``producer_offset`` increments monotonically per session.
- A failing emitter never breaks action execution and never alters the result.
- ``ValkeyHistoryEmitter`` issues an ``XADD`` to the shared ``history:ingest``
  stream with a JSON envelope.
- The envelope builder matches the shared cross-service contract.
"""

from __future__ import annotations

import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from game_service.coordination.history_emitter import (
    ACTOR,
    ENVELOPE_FIELD,
    ENVELOPE_VERSION,
    EVENT_TYPE_STATE,
    GENERIC_ACTION_PATH,
    HISTORY_INGEST_STREAM,
    NullHistoryEmitter,
    ValkeyHistoryEmitter,
    build_history_emitter,
    build_state_envelope,
)
from game_service.logic.actions import DrawCardAction, NextStepAction
import game_service.logic.session as session_module

from .session_manager_test_support import make_session


class FakeHistoryEmitter:
    """Records every emitted state event and hands out durable offsets."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._offsets: dict[str, int] = {}

    async def next_producer_offset(self, game_id):
        nxt = self._offsets.get(game_id, 0) + 1
        self._offsets[game_id] = nxt
        return nxt

    async def emit_state_event(
        self, *, game_id, producer_offset, state, action_args=None, plugin_name=None
    ) -> None:
        self.events.append(
            {
                "game_id": game_id,
                "producer_offset": producer_offset,
                "state": state,
                "action_args": action_args,
                "plugin_name": plugin_name,
            }
        )


class FailingHistoryEmitter:
    """Always raises to prove emission failure cannot break the action."""

    def __init__(self) -> None:
        self.calls = 0
        self._offset = 0

    async def next_producer_offset(self, game_id):
        self._offset += 1
        return self._offset

    async def emit_state_event(
        self, *, game_id, producer_offset, state, action_args=None, plugin_name=None
    ) -> None:
        self.calls += 1
        raise RuntimeError("history bus is down")


class NoOffsetHistoryEmitter:
    """Offset allocation always fails (returns None); emission must be skipped."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def next_producer_offset(self, game_id):
        return None

    async def emit_state_event(
        self, *, game_id, producer_offset, state, action_args=None, plugin_name=None
    ) -> None:  # pragma: no cover - must never be reached
        self.events.append({"game_id": game_id})


class _RecordedSpan:
    def __init__(self, name, initial, sink):
        self.name = name
        self.attributes = dict(initial or {})
        sink.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def set_attribute(self, key, value):
        self.attributes[key] = value


class _RecordedTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name, attributes=None):
        return _RecordedSpan(name, attributes, self.spans)


def _arm_successful_action(session, state) -> None:
    """Configure channel mocks so ``execute_action`` completes successfully."""
    session.channel.push = AsyncMock(side_effect=[{}, state])
    session.channel.wait_for_event = AsyncMock(
        return_value=MagicMock(event="state_update")
    )
    session.channel.wait_for_state_update = AsyncMock(return_value=state)


# ---------------------------------------------------------------------------
# Envelope contract
# ---------------------------------------------------------------------------


def test_build_state_envelope_matches_shared_contract():
    env = build_state_envelope(
        game_id="game-123",
        producer_offset=7,
        state={"game": {"mode": "in progress"}},
    )

    assert env["envelope_version"] == ENVELOPE_VERSION
    assert env["actor"] == ACTOR == "game-service"
    assert env["event_type"] == EVENT_TYPE_STATE
    assert env["game_id"] == "game-123"
    assert env["producer_offset"] == 7
    assert env["payload"]["status"] == "in progress"
    assert env["payload"]["state"] == {"game": {"mode": "in progress"}}
    assert isinstance(env["payload"]["state_digest"], str)
    assert isinstance(env["idempotency_key"], str)
    assert "occurred_at" in env and isinstance(env["occurred_at"], str)
    # The history-service assigns these; producers MUST NOT set them.
    assert "seq" not in env
    assert "recorded_at" not in env


def test_envelope_carries_replayable_action_when_supplied():
    action_args = {"type": "draw_card", "player": "player1", "count": 1}
    env = build_state_envelope(
        game_id="g",
        producer_offset=1,
        state={"game": {"mode": "in progress"}},
        action_args=action_args,
    )
    # The history-service replays via POST /games/{id}/{action_path} with
    # action_args; action_path is the generic actions endpoint suffix.
    assert env["payload"]["action_path"] == GENERIC_ACTION_PATH == "actions"
    assert env["payload"]["action_args"] == action_args


def test_envelope_without_action_is_not_replayable():
    env = build_state_envelope(
        game_id="g", producer_offset=1, state={"game": {"mode": "in progress"}}
    )
    assert "action_path" not in env["payload"]
    assert "action_args" not in env["payload"]


def test_idempotency_key_is_stable_for_same_offset():
    a = build_state_envelope(game_id="g", producer_offset=1, state={"game": {}})
    b = build_state_envelope(game_id="g", producer_offset=1, state={"game": {}})
    c = build_state_envelope(game_id="g", producer_offset=2, state={"game": {}})
    assert a["idempotency_key"] == b["idempotency_key"]
    assert a["idempotency_key"] != c["idempotency_key"]


def test_status_defaults_to_unknown_for_malformed_state():
    env = build_state_envelope(game_id="g", producer_offset=1, state=None)
    assert env["payload"]["status"] == "unknown"


@pytest.mark.parametrize("status", ["in progress", "win", "loss", "unknown"])
def test_status_extracted_from_game_mode(status):
    env = build_state_envelope(
        game_id="g", producer_offset=1, state={"game": {"mode": status}}
    )
    assert env["payload"]["status"] == status


# ---------------------------------------------------------------------------
# Emission per executed action
# ---------------------------------------------------------------------------


async def test_execute_action_emits_one_event_with_game_id_and_status():
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "win"}}
    _arm_successful_action(session, state)

    result = await session.execute_action(NextStepAction())

    assert result == state  # action result unchanged
    assert len(emitter.events) == 1
    event = emitter.events[0]
    assert event["game_id"] == session.session_id
    assert event["state"] == state
    assert event["producer_offset"] == 1
    # The executed action is captured in replayable form for restore.
    assert event["action_args"] == {"type": "next_step"}
    # The session plugin slug rides on every state event so a branchable
    # restore can materialize a fresh session even without a snapshot.
    assert event["plugin_name"] == "marvel-champions"


async def test_dragncards_action_span_has_safe_platform_seat_and_outcome(monkeypatch):
    recorded = _RecordedTracer()
    monkeypatch.setattr(session_module, "tracer", recorded)
    session = make_session()
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    await session.execute_action(DrawCardAction(player_n="player2"))

    spans = [
        span for span in recorded.spans if span.name == "game_session.execute_action"
    ]
    assert len(spans) == 1
    assert spans[0].attributes == {
        "game.action.name": "DrawCardAction",
        "game.platform": "dragncards",
        "game.seat": "player2",
        "game.outcome": "succeeded",
    }


async def test_producer_offset_increments_per_action():
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter

    for mode in ("in progress", "in progress", "loss"):
        state = {"game": {"mode": mode}}
        _arm_successful_action(session, state)
        await session.execute_action(NextStepAction())

    assert [e["producer_offset"] for e in emitter.events] == [1, 2, 3]
    assert emitter.events[-1]["state"]["game"]["mode"] == "loss"


async def test_emission_failure_does_not_break_action():
    emitter = FailingHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    # Must NOT raise even though the emitter raises.
    result = await session.execute_action(NextStepAction())

    assert result == state
    assert emitter.calls == 1


async def test_no_emitter_configured_defaults_to_null_emitter():
    session = make_session()
    assert isinstance(session.history_emitter, NullHistoryEmitter)
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)
    # Should simply not raise.
    assert await session.execute_action(NextStepAction()) == state


async def test_emission_skipped_when_durable_offset_unavailable():
    """If the durable offset cannot be allocated, no event is emitted."""
    emitter = NoOffsetHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    result = await session.execute_action(NextStepAction())

    assert result == state  # action result unchanged
    assert emitter.events == []  # emission skipped, no collision-prone offset


async def test_ephemeral_session_emits_no_history():
    """A view-only ephemeral reconstruction session never emits history events."""
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.ephemeral = True
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    result = await session.execute_action(NextStepAction())

    assert result == state  # action result unchanged
    assert emitter.events == []  # nothing reaches the history bus


async def test_failed_action_does_not_emit_or_advance_offset():
    """A rejected/aborted action must not record a move or consume an offset."""
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter

    # A successful action first claims offset 1.
    ok_state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, ok_state)
    await session.execute_action(NextStepAction())
    assert [e["producer_offset"] for e in emitter.events] == [1]

    # Now an action whose resulting state carries an in-game ABORT error.
    aborted_state = {
        "game": {"mode": "in progress", "messages": ["ABORT: not your turn"]}
    }
    _arm_successful_action(session, aborted_state)
    await session.execute_action(NextStepAction())

    # No new event, and the offset was not advanced (next success is 2, not 3).
    assert [e["producer_offset"] for e in emitter.events] == [1]
    ok_state2 = {"game": {"mode": "win"}}
    _arm_successful_action(session, ok_state2)
    await session.execute_action(NextStepAction())
    assert [e["producer_offset"] for e in emitter.events] == [1, 2]


# ---------------------------------------------------------------------------
# Emission for non-execute_action state mutations
# (load_prebuilt_deck / load_state / reset_game)
# ---------------------------------------------------------------------------


async def test_load_prebuilt_deck_emits_one_state_event():
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress", "loadedCardIds": ["c1"]}}
    _arm_successful_action(session, state)

    result = await session.load_prebuilt_deck("deck-1")

    assert result == state  # deck-load result unchanged
    assert len(emitter.events) == 1
    event = emitter.events[0]
    assert event["game_id"] == session.session_id
    assert event["state"] == state
    assert event["producer_offset"] == 1
    assert event["plugin_name"] == "marvel-champions"
    # The deck load is replayable via the raw LOAD_CARDS action.
    assert event["action_args"] == {
        "type": "raw",
        "action_list": ["LOAD_CARDS", "deck-1"],
        "description": "Loaded prebuilt deck deck-1",
        "player_n": "player1",
    }


async def test_load_prebuilt_deck_emission_failure_does_not_break():
    emitter = FailingHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    # Must NOT raise even though the emitter raises.
    result = await session.load_prebuilt_deck("deck-1")

    assert result == state
    assert emitter.calls == 1


async def test_load_state_emits_one_state_event():
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress", "roundNumber": 4}}
    _arm_successful_action(session, state)

    result = await session.load_state(
        {
            "schema_version": 1,
            "plugin_name": "marvel-champions",
            "game": {"mode": "in progress", "roundNumber": 4},
        }
    )

    assert result == state  # load result unchanged
    assert len(emitter.events) == 1
    event = emitter.events[0]
    assert event["game_id"] == session.session_id
    assert event["state"] == state
    assert event["producer_offset"] == 1
    assert event["plugin_name"] == "marvel-champions"
    # A raw state load carries no replayable action.
    assert event["action_args"] is None


async def test_load_state_emission_failure_does_not_break():
    emitter = FailingHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    # Must NOT raise even though the emitter raises.
    result = await session.load_state(
        {
            "schema_version": 1,
            "plugin_name": "marvel-champions",
            "game": {"mode": "in progress"},
        }
    )

    assert result == state
    assert emitter.calls == 1


async def test_reset_game_emits_one_state_event():
    emitter = FakeHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    result = await session.reset_game()

    assert result == state  # reset result unchanged
    assert len(emitter.events) == 1
    event = emitter.events[0]
    assert event["game_id"] == session.session_id
    assert event["state"] == state
    assert event["producer_offset"] == 1
    assert event["plugin_name"] == "marvel-champions"
    # A room-level reset carries no replayable action.
    assert event["action_args"] is None


async def test_reset_game_emission_failure_does_not_break():
    emitter = FailingHistoryEmitter()
    session = make_session()
    session.history_emitter = emitter
    state = {"game": {"mode": "in progress"}}
    _arm_successful_action(session, state)

    # Must NOT raise even though the emitter raises.
    result = await session.reset_game()

    assert result == state
    assert emitter.calls == 1


# ---------------------------------------------------------------------------
# ValkeyHistoryEmitter -> XADD
# ---------------------------------------------------------------------------


async def test_valkey_emitter_xadds_json_envelope():
    emitter = ValkeyHistoryEmitter("redis://localhost:6380/0")
    captured: list[tuple] = []

    async def fake_execute(*parts):
        captured.append(parts)
        return "1-0"

    emitter._conn.execute = fake_execute  # type: ignore[assignment]

    await emitter.emit_state_event(
        game_id="game-xyz",
        producer_offset=2,
        state={"game": {"mode": "win"}},
    )

    assert len(captured) == 1
    parts = captured[0]
    assert parts[0] == "XADD"
    assert parts[1] == HISTORY_INGEST_STREAM
    assert "MAXLEN" in parts
    # Field name MUST match the history-service ingester + orchestrator producer.
    assert parts[-2] == ENVELOPE_FIELD == "envelope_json"
    envelope = json.loads(parts[-1])
    assert envelope["game_id"] == "game-xyz"
    assert envelope["actor"] == "game-service"
    assert envelope["producer_offset"] == 2
    assert envelope["payload"]["status"] == "win"


async def test_valkey_emitter_swallows_publish_errors():
    emitter = ValkeyHistoryEmitter("redis://localhost:6380/0")

    async def boom(*parts):
        raise OSError("connection refused")

    emitter._conn.execute = boom  # type: ignore[assignment]

    # Best-effort: must not raise.
    await emitter.emit_state_event(
        game_id="g", producer_offset=1, state={"game": {"mode": "loss"}}
    )


async def test_valkey_emitter_offset_uses_durable_incr():
    """The offset is sourced from a Valkey INCR on the shared history Valkey."""
    emitter = ValkeyHistoryEmitter("redis://localhost:6380/0")
    captured: list[tuple] = []

    async def fake_execute(*parts):
        captured.append(parts)
        return b"5"

    emitter._conn.execute = fake_execute  # type: ignore[assignment]

    offset = await emitter.next_producer_offset("game-abc")

    assert offset == 5
    assert captured == [("INCR", "game-service:history-offset:game-abc")]


async def test_valkey_emitter_offset_returns_none_on_failure():
    """A failed offset INCR returns None so the caller skips emission."""
    emitter = ValkeyHistoryEmitter("redis://localhost:6380/0")

    async def boom(*parts):
        raise OSError("connection refused")

    emitter._conn.execute = boom  # type: ignore[assignment]

    assert await emitter.next_producer_offset("g") is None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_build_history_emitter_disabled_returns_null():
    assert isinstance(
        build_history_emitter(enabled=False, valkey_url="redis://x:6380"),
        NullHistoryEmitter,
    )


def test_build_history_emitter_no_url_returns_null():
    assert isinstance(
        build_history_emitter(enabled=True, valkey_url=None), NullHistoryEmitter
    )


def test_build_history_emitter_enabled_returns_valkey_emitter():
    assert isinstance(
        build_history_emitter(enabled=True, valkey_url="redis://localhost:6380/0"),
        ValkeyHistoryEmitter,
    )


# ---------------------------------------------------------------------------
# Restore support: snapshot load into a target session, then forward replay
# ---------------------------------------------------------------------------


async def test_restore_loads_snapshot_then_replays_actions_forward():
    """A history-supplied snapshot loads into a target session and replayed
    actions are then applied forward via the normal action execution path.

    This mirrors the history-service restore flow (PUT snapshot, then execute
    game-mutating actions forward) and confirms the existing endpoints suffice.
    """
    emitter = FakeHistoryEmitter()
    session = make_session()  # plugin_name="marvel-champions"
    session.history_emitter = emitter

    # Step 1: load a history-supplied snapshot (the PUT /snapshot path).
    snapshot_state = {"game": {"mode": "in progress", "roundNumber": 4}}
    session.channel.push = AsyncMock(side_effect=[{}, snapshot_state])
    session.channel.wait_for_event = AsyncMock(
        return_value=MagicMock(event="state_update")
    )
    session.channel.wait_for_state_update = AsyncMock(return_value=snapshot_state)

    loaded = await session.load_state(
        {
            "schema_version": 1,
            "plugin_name": "marvel-champions",
            "game": {"mode": "in progress", "roundNumber": 4},
        }
    )
    assert loaded == snapshot_state
    # The snapshot load is a state mutation, so it snapshots the loaded board as
    # a game_state event carrying no replayable action.
    assert len(emitter.events) == 1
    assert emitter.events[0]["state"] == snapshot_state
    assert emitter.events[0]["action_args"] is None

    # Step 2: replay a forward game-mutating action into the restored session.
    replay_state = {"game": {"mode": "win", "roundNumber": 5}}
    _arm_successful_action(session, replay_state)
    replayed = await session.execute_action(NextStepAction())

    assert replayed == replay_state
    assert len(emitter.events) == 2
    assert emitter.events[-1]["state"] == replay_state
