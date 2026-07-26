from __future__ import annotations

import pytest

from eval_service.judge.assembly import (
    BoundaryUndetectedError,
    assemble_move_input,
    assemble_round_input,
    detect_round_boundaries,
    round_number_of,
)
from tests.unit.conftest import agent_event, make_event, state_event


def _recorded_game(game_id="g1"):
    # seq1 state r1, seq2 agent move, seq3 state r1, seq4 agent move,
    # seq5 state r2 (round change), seq6 agent move, seq7 state r2 terminal win
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2, action="play_a"),
        state_event(game_id=game_id, seq=3, round_number=1),
        agent_event(game_id=game_id, seq=4, action="play_b"),
        state_event(game_id=game_id, seq=5, round_number=2),
        agent_event(game_id=game_id, seq=6, action="attack"),
        state_event(game_id=game_id, seq=7, round_number=2, status="win"),
    ]


def test_move_input_correlates_prior_and_resulting_state():
    events = _recorded_game()
    move = assemble_move_input(events, target_seq=4)
    assert move.intended_action == "play_b"
    assert move.reasoning == "because"
    assert move.arguments == {"card_id": "c4"}
    # prior state is the nearest game-service at/<= seq4 -> seq3 (round 1)
    assert move.prior_state["roundNumber"] == 1
    # resulting state is the nearest game-service at/>= seq4 -> seq5 (round 2)
    assert move.resulting_state["roundNumber"] == 2


def test_move_input_rejects_non_agent_seq():
    events = _recorded_game()
    with pytest.raises(ValueError):
        assemble_move_input(events, target_seq=1)


def test_round_boundary_detection_with_change_and_terminal():
    events = _recorded_game()
    boundaries = detect_round_boundaries(events)
    # round 1 closes at seq4 (last seq before the round-2 state at seq5);
    # round 2 closes at the terminal win at seq7.
    assert (1, 1, 4) in boundaries
    assert boundaries[-1] == (2, 5, 7)


def test_round_boundary_terminal_fallback_closes_final_round():
    # No round-number change, only a terminal status closes the round.
    events = [
        state_event(game_id="g2", seq=1, round_number=1),
        agent_event(game_id="g2", seq=2),
        state_event(game_id="g2", seq=3, round_number=1, status="loss"),
    ]
    boundaries = detect_round_boundaries(events)
    assert boundaries == [(1, 1, 3)]


def test_round_boundary_undetected_when_no_round_numbers():
    # game-service events without any round number -> no boundaries detected.
    events = [
        make_event(
            game_id="g3",
            seq=1,
            actor="game-service",
            payload={"state": {"mode": "in progress"}, "status": "in progress"},
        ),
        agent_event(game_id="g3", seq=2),
    ]
    assert detect_round_boundaries(events) == []
    with pytest.raises(BoundaryUndetectedError):
        assemble_round_input(events, closing_seq=1)


def test_assemble_round_input_spans_round_moves():
    events = _recorded_game()
    rnd = assemble_round_input(events, closing_seq=4)
    assert rnd.round_number == 1
    assert (rnd.from_seq, rnd.to_seq) == (1, 4)
    # moves within round 1: seq2 and seq4
    assert [m.target_seq for m in rnd.moves] == [2, 4]


def test_round_number_of_reads_raw_game_shape():
    raw_state = make_event(
        game_id="g4",
        seq=1,
        actor="game-service",
        payload={"state": {"game": {"roundNumber": 5}}},
    )
    assert round_number_of(raw_state) == 5
