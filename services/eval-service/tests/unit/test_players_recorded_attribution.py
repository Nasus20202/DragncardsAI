"""Attribution when the producer recorded the acting seat.

An orchestrated multi-player game runs one agent per seat, so the acting player
is known at emission time and stamped on the move. That is ground truth and must
outrank every inference the eval-service would otherwise make.
"""

from __future__ import annotations

from eval_service.runtime.players import attribute_move, players_in_span
from tests.unit.conftest import agent_event, make_event, state_event


def _recorded_move(*, game_id, seq, player, action="play"):
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="agent",
        event_type="agent_move",
        payload={
            "intended_action": action,
            "reasoning": "because",
            "arguments": {"card_id": f"c{seq}"},
            "player": player,
        },
    )


def _two_player_state(*, game_id, seq, round_number, first_player="player1"):
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="game-service",
        event_type="game_state",
        payload={
            "state": {
                "game": {
                    "roundNumber": round_number,
                    "numPlayers": 2,
                    "firstPlayer": first_player,
                    "playerData": {"player1": {}, "player2": {}},
                }
            },
            "status": "in progress",
        },
    )


def test_recorded_player_wins_over_rotation_inference():
    # By rotation the first move of the round would be player1; the move itself
    # says player2, and the recorded fact must win.
    events = [
        _two_player_state(game_id="g", seq=1, round_number=1),
        _recorded_move(game_id="g", seq=2, player="player2"),
        _two_player_state(game_id="g", seq=3, round_number=1),
    ]

    assert attribute_move(events, 2) == "player2"


def test_recorded_player_wins_when_state_is_not_derivable():
    # No game-service state at all: inference would collapse to player1.
    events = [_recorded_move(game_id="g", seq=1, player="player3")]

    assert attribute_move(events, 1) == "player3"


def test_recorded_player_wins_over_single_player_shortcircuit():
    events = [
        state_event(game_id="g", seq=1, round_number=1),
        _recorded_move(game_id="g", seq=2, player="player2"),
    ]

    assert attribute_move(events, 2) == "player2"


def test_recorded_player_wins_over_an_argument_hint():
    events = [
        _two_player_state(game_id="g", seq=1, round_number=1),
        make_event(
            game_id="g",
            seq=2,
            actor="agent",
            event_type="agent_move",
            payload={
                "intended_action": "play",
                "arguments": {"player_n": "player1"},
                "player": "player2",
            },
        ),
    ]

    assert attribute_move(events, 2) == "player2"


def test_malformed_recorded_player_falls_back_to_inference():
    events = [
        state_event(game_id="g", seq=1, round_number=1),
        make_event(
            game_id="g",
            seq=2,
            actor="agent",
            event_type="agent_move",
            payload={"intended_action": "play", "player": "villain"},
        ),
    ]

    assert attribute_move(events, 2) == "player1"


def test_legacy_events_keep_heuristic_attribution():
    events = [
        _two_player_state(game_id="g", seq=1, round_number=1),
        agent_event(game_id="g", seq=2),
        agent_event(game_id="g", seq=3),
    ]

    assert attribute_move(events, 2) == "player1"
    assert attribute_move(events, 3) == "player2"


def test_span_reports_every_recorded_seat():
    events = [
        _two_player_state(game_id="g", seq=1, round_number=1),
        _recorded_move(game_id="g", seq=2, player="player2"),
        _recorded_move(game_id="g", seq=3, player="player1"),
        _two_player_state(game_id="g", seq=4, round_number=1),
    ]

    assert players_in_span(events, 1, 4) == ["player1", "player2"]
