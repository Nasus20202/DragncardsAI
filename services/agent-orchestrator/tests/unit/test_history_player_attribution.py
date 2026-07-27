from __future__ import annotations

import pytest

from agent_orchestrator.runtime.history_emitter import (
    HistoryEventEmitter,
    InMemoryHistoryEventBus,
)


def test_envelope_carries_the_seat_when_one_is_supplied():
    envelope = HistoryEventEmitter.build_envelope(
        game_id="game-1",
        intended_action="next_step",
        reasoning="advance",
        arguments={},
        conversation_context=[],
        producer_offset=1,
        player="player2",
    )

    assert envelope["payload"]["player"] == "player2"


def test_envelope_omits_the_seat_for_moves_that_belong_to_no_player():
    envelope = HistoryEventEmitter.build_envelope(
        game_id="game-1",
        intended_action="villain_encounter_phase",
        reasoning="villain phase",
        arguments={},
        conversation_context=[],
        producer_offset=1,
    )

    # Absent, not null: "no seat" must be distinguishable from "seat unknown".
    assert "player" not in envelope["payload"]


@pytest.mark.asyncio
async def test_emitted_move_publishes_the_seat():
    bus = InMemoryHistoryEventBus()
    emitter = HistoryEventEmitter(bus=bus)

    await emitter.emit_agent_move(
        game_id="game-1",
        intended_action="draw_card",
        reasoning="",
        arguments={},
        conversation_context=[],
        player="player1",
    )

    assert bus.events[0]["payload"]["player"] == "player1"
