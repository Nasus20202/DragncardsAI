from __future__ import annotations

from eval_service.runtime.players import attribute_move, players_in_span
from tests.unit.conftest import agent_event, make_event, state_event


def _raw_state_event(*, game_id, seq, round_number, num_players, first_player):
    """A game-service event carrying raw DragnCards state (state.game.*)."""
    player_data = {f"player{i}": {"alias": f"p{i}"} for i in range(1, num_players + 1)}
    return make_event(
        game_id=game_id,
        seq=seq,
        actor="game-service",
        event_type="game_state",
        payload={
            "state": {
                "game": {
                    "roundNumber": round_number,
                    "numPlayers": num_players,
                    "firstPlayer": first_player,
                    "playerData": player_data,
                }
            },
            "status": "in progress",
        },
    )


def test_single_player_move_attributes_to_player1():
    events = [
        state_event(game_id="g", seq=1, round_number=1),
        agent_event(game_id="g", seq=2),
        state_event(game_id="g", seq=3, round_number=1),
    ]
    assert attribute_move(events, 2) == "player1"


def test_single_player_span_is_player1_only():
    events = [
        state_event(game_id="g", seq=1, round_number=1),
        agent_event(game_id="g", seq=2),
        agent_event(game_id="g", seq=3),
        state_event(game_id="g", seq=4, round_number=1, status="win"),
    ]
    assert players_in_span(events, 1, 4) == ["player1"]


def test_two_player_turn_alternation_by_first_player_rotation():
    # firstPlayer=player1 -> the round's agent moves alternate player1, player2.
    events = [
        _raw_state_event(
            game_id="g", seq=1, round_number=1, num_players=2, first_player="player1"
        ),
        agent_event(game_id="g", seq=2),  # 1st move of round -> player1
        agent_event(game_id="g", seq=3),  # 2nd move of round -> player2
        agent_event(game_id="g", seq=4),  # 3rd move of round -> player1
        _raw_state_event(
            game_id="g", seq=5, round_number=1, num_players=2, first_player="player1"
        ),
    ]
    assert attribute_move(events, 2) == "player1"
    assert attribute_move(events, 3) == "player2"
    assert attribute_move(events, 4) == "player1"
    assert players_in_span(events, 1, 5) == ["player1", "player2"]


def test_first_player_rotation_starts_at_recorded_first_player():
    # firstPlayer=player2 -> the rotation starts at player2.
    events = [
        _raw_state_event(
            game_id="g", seq=1, round_number=1, num_players=2, first_player="player2"
        ),
        agent_event(game_id="g", seq=2),  # 1st move -> player2
        agent_event(game_id="g", seq=3),  # 2nd move -> player1
    ]
    assert attribute_move(events, 2) == "player2"
    assert attribute_move(events, 3) == "player1"


def test_explicit_player_hint_on_arguments_wins():
    events = [
        _raw_state_event(
            game_id="g", seq=1, round_number=1, num_players=2, first_player="player1"
        ),
        make_event(
            game_id="g",
            seq=2,
            actor="agent",
            event_type="move",
            payload={
                "intended_action": "play",
                "reasoning": "r",
                "arguments": {"player_n": "player2"},
            },
        ),
    ]
    # Rotation would say player1 (1st move) but the explicit hint says player2.
    assert attribute_move(events, 2) == "player2"


def test_players_in_span_orders_seats_numerically():
    events = [
        _raw_state_event(
            game_id="g", seq=1, round_number=1, num_players=3, first_player="player3"
        ),
        agent_event(game_id="g", seq=2),  # player3
        agent_event(game_id="g", seq=3),  # player1
        agent_event(game_id="g", seq=4),  # player2
    ]
    assert players_in_span(events, 1, 4) == ["player1", "player2", "player3"]
