"""The session mode carried on emitted history events.

The mode is stamped by :func:`stamp_session_mode`, which OMITS the key for chat
rather than writing ``"chat"``. Two properties follow, and both are pinned here:

- an orchestrated event states its mode, alongside the seat when it has one and
  with no seat when it is the coordinating agent's own bookkeeping;
- a chat event's payload is byte-identical to what it was before the mode existed,
  which is what makes "the addition changes no stored meaning" a fact about the
  bytes rather than an assertion about intent.
"""

from __future__ import annotations

import pytest

from agent_orchestrator.runtime.history_emitter import (
    HISTORY_EVENT_TYPE_ILLEGAL_ACTION,
    HistoryEventEmitter,
    InMemoryHistoryEventBus,
    stamp_session_mode,
)
from agent_orchestrator.runtime.session_modes import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
)
from agent_orchestrator.runtime.platforms import PLATFORM_MARVEL_LCG


def _move(**overrides):
    kwargs = {
        "game_id": "game-1",
        "intended_action": "move_card",
        "reasoning": "advance",
        "arguments": {},
        "conversation_context": [],
        "producer_offset": 1,
    }
    kwargs.update(overrides)
    return HistoryEventEmitter.build_envelope(**kwargs)


# --- chat mode stores exactly what it stored before ---------------------------


def test_a_chat_move_payload_is_byte_identical_to_the_pre_mode_payload():
    payload = _move()["payload"]

    assert payload == {
        "intended_action": "move_card",
        "reasoning": "advance",
        "arguments": {},
        "conversation_context": [],
    }
    assert "session_mode" not in payload


def test_a_chat_user_prompt_payload_is_byte_identical_to_the_pre_mode_payload():
    envelope = HistoryEventEmitter.build_user_prompt_envelope(
        game_id="game-1", prompt="attack the villain", producer_offset=1
    )

    assert envelope["payload"] == {"prompt": "attack the villain"}


def test_the_chat_default_matches_an_explicit_chat_mode():
    assert _move()["payload"] == _move(session_mode=SESSION_MODE_CHAT)["payload"]


def test_platform_is_carried_as_a_top_level_envelope_field():
    move = _move(platform=PLATFORM_MARVEL_LCG)
    prompt = HistoryEventEmitter.build_user_prompt_envelope(
        game_id="game-1",
        prompt="play",
        producer_offset=2,
        platform=PLATFORM_MARVEL_LCG,
    )
    finding = HistoryEventEmitter.build_illegal_action_envelope(
        game_id="game-1",
        player="player1",
        violation="illegal action",
        required_undo="undo it",
        producer_offset=3,
        platform=PLATFORM_MARVEL_LCG,
    )

    assert move["platform"] == PLATFORM_MARVEL_LCG
    assert prompt["platform"] == PLATFORM_MARVEL_LCG
    assert finding["platform"] == PLATFORM_MARVEL_LCG


def test_the_stamp_helper_writes_nothing_for_chat_and_the_mode_otherwise():
    chat: dict = {}
    stamp_session_mode(chat, SESSION_MODE_CHAT)
    assert chat == {}

    orchestrated: dict = {}
    stamp_session_mode(orchestrated, SESSION_MODE_ORCHESTRATED)
    assert orchestrated == {"session_mode": SESSION_MODE_ORCHESTRATED}


# --- orchestrated mode states itself, with and without a seat ----------------


def test_an_orchestrated_seats_move_states_the_mode_and_the_seat():
    payload = _move(session_mode=SESSION_MODE_ORCHESTRATED, player="player2")["payload"]

    assert payload["session_mode"] == SESSION_MODE_ORCHESTRATED
    assert payload["player"] == "player2"


def test_the_orchestrators_own_event_states_the_mode_and_carries_no_seat():
    """The orchestrator's bookkeeping must stay distinguishable from a seat's play."""
    payload = _move(
        intended_action="villain_encounter_phase",
        session_mode=SESSION_MODE_ORCHESTRATED,
    )["payload"]

    assert payload["session_mode"] == SESSION_MODE_ORCHESTRATED
    # Absent, not null: "no seat" must be distinguishable from "seat unknown".
    assert "player" not in payload


def test_an_orchestrated_user_prompt_states_the_mode():
    envelope = HistoryEventEmitter.build_user_prompt_envelope(
        game_id="game-1",
        prompt="take the villain down",
        producer_offset=1,
        session_mode=SESSION_MODE_ORCHESTRATED,
    )

    assert envelope["payload"] == {
        "prompt": "take the villain down",
        "session_mode": SESSION_MODE_ORCHESTRATED,
    }


@pytest.mark.asyncio
async def test_the_emitted_move_and_prompt_publish_the_mode():
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus)

    await emitter.emit_user_prompt(
        game_id="game-1",
        prompt="play a turn",
        session_mode=SESSION_MODE_ORCHESTRATED,
        platform=PLATFORM_MARVEL_LCG,
    )
    await emitter.emit_agent_move(
        game_id="game-1",
        intended_action="draw_card",
        reasoning="",
        arguments={},
        conversation_context=[],
        player="player1",
        session_mode=SESSION_MODE_ORCHESTRATED,
        platform=PLATFORM_MARVEL_LCG,
    )

    prompt_event, move_event = bus.events
    assert prompt_event["payload"]["session_mode"] == SESSION_MODE_ORCHESTRATED
    assert move_event["payload"]["session_mode"] == SESSION_MODE_ORCHESTRATED
    assert move_event["payload"]["player"] == "player1"
    assert prompt_event["platform"] == PLATFORM_MARVEL_LCG
    assert move_event["platform"] == PLATFORM_MARVEL_LCG


@pytest.mark.asyncio
async def test_a_chat_session_publishes_no_mode_key_on_either_event():
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus)

    await emitter.emit_user_prompt(game_id="game-1", prompt="play a turn")
    await emitter.emit_agent_move(
        game_id="game-1",
        intended_action="draw_card",
        reasoning="",
        arguments={},
        conversation_context=[],
    )

    for envelope in bus.events:
        assert envelope["platform"] == "dragncards"
        assert "session_mode" not in envelope["payload"]


# --- illegal-action findings --------------------------------------------------


@pytest.mark.asyncio
async def test_an_illegal_action_finding_is_an_agent_event_of_its_own_type():
    """A new orchestrator concern arrives as a new event type, not a new actor.

    history-service pins ``actor`` to a fixed literal set, so a finding rides on
    the ``agent`` actor and is told apart from a move by its event type.
    """
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus)

    envelope = await emitter.emit_illegal_action(
        game_id="game-1",
        player="player2",
        violation="attacked with an exhausted hero",
        required_undo="ready the hero and undo the attack",
        round_number=3,
    )

    assert envelope is not None
    assert envelope["actor"] == "agent"
    assert envelope["event_type"] == HISTORY_EVENT_TYPE_ILLEGAL_ACTION
    assert envelope["platform"] == "dragncards"
    assert envelope["payload"] == {
        "player": "player2",
        "violation": "attacked with an exhausted hero",
        "required_undo": "ready the hero and undo the attack",
        "status": "open",
        "session_mode": SESSION_MODE_ORCHESTRATED,
        "round_number": 3,
    }
    assert "conversation_context" not in envelope["payload"]
    assert bus.events == [envelope]


@pytest.mark.asyncio
async def test_a_resolved_finding_carries_its_status_and_note():
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus)

    envelope = await emitter.emit_illegal_action(
        game_id="game-1",
        player="player1",
        violation="played an ally with no resources paid",
        required_undo="return the ally to hand",
        status="resolved",
        resolution_note="seat returned the ally to hand",
    )

    assert envelope is not None
    assert envelope["payload"]["status"] == "resolved"
    assert envelope["payload"]["resolution_note"] == "seat returned the ally to hand"
    # Omitted rather than null when the caller had none to give.
    assert "round_number" not in envelope["payload"]


@pytest.mark.asyncio
async def test_a_finding_takes_a_producer_offset_like_every_other_event():
    """Findings share the per-game offset sequence, so ordering stays total."""
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus)

    await emitter.emit_agent_move(
        game_id="game-1",
        intended_action="move_card",
        reasoning="",
        arguments={},
        conversation_context=[],
    )
    finding = await emitter.emit_illegal_action(
        game_id="game-1",
        player="player1",
        violation="illegal play",
        required_undo="undo it",
    )

    assert finding is not None
    assert finding["producer_offset"] == 2


@pytest.mark.asyncio
async def test_a_disabled_emitter_publishes_no_finding():
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus, enabled=False)

    result = await emitter.emit_illegal_action(
        game_id="game-1",
        player="player1",
        violation="illegal play",
        required_undo="undo it",
    )

    assert result is None
    assert bus.events == []
