"""Seat vocabulary.

A DragnCards seat is a key of the room's seat map, so the value space matters:
a number is not a seat, and an entry written under one is invisible to every
seat lookup. These tests pin that down, plus the two state shapes occupancy
arrives in.
"""

from __future__ import annotations

import pytest

from game_service.logic.seats import (
    MAX_SEATS,
    SEAT_IDS,
    normalise_seat_id,
    seat_held_by,
    seat_occupants,
    seats_in_play,
    seats_to_claim,
)


@pytest.mark.parametrize("seat", SEAT_IDS)
def test_every_seat_id_normalises_to_itself(seat):
    assert normalise_seat_id(seat) == seat


@pytest.mark.parametrize("bad", [0, 1, 2, True, None, 1.0])
def test_a_number_is_not_a_seat(bad):
    """The bug this replaces: an int wrote a seat-map key naming no seat."""
    with pytest.raises(ValueError):
        normalise_seat_id(bad)


@pytest.mark.parametrize("bad", ["player0", "player5", "shared", "PLAYER1", ""])
def test_unknown_seat_names_are_refused(bad):
    with pytest.raises(ValueError):
        normalise_seat_id(bad)


def test_player_info_is_read_as_occupancy():
    state = {
        "game": {
            "playerInfo": {
                "player1": {"id": 10, "alias": "dev_user"},
                "player2": None,
                "player3": {"id": None},
            }
        }
    }
    assert seat_occupants(state) == {
        "player1": 10,
        "player2": None,
        "player3": None,
        "player4": None,
    }


def test_player_info_at_the_envelope_top_level_is_read_too():
    """Room state carries playerInfo beside `game`, not only inside it."""
    state = {"playerInfo": {"player1": {"id": 7}}, "game": {}}
    assert seat_occupants(state)["player1"] == 7


def test_player_data_is_the_fallback_shape():
    state = {
        "game": {
            "playerData": {
                "player1": {"user_id": 10},
                "player2": {"user_id": None},
                "player3": {},
            }
        }
    }
    assert seat_occupants(state)["player1"] == 10
    assert seat_occupants(state)["player2"] is None


def test_player_info_wins_over_player_data():
    state = {
        "game": {
            "playerInfo": {"player1": {"id": 10}},
            "playerData": {"player1": {"user_id": 99}},
        }
    }
    assert seat_occupants(state)["player1"] == 10


@pytest.mark.parametrize("state", [None, "not a dict", {}, {"game": None}])
def test_unreadable_state_reports_every_seat_vacant(state):
    assert seat_occupants(state) == {seat: None for seat in SEAT_IDS}


def test_seats_in_play_is_a_prefix_of_the_seat_ids():
    assert seats_in_play(1) == ["player1"]
    assert seats_in_play(2) == ["player1", "player2"]
    assert seats_in_play(0) == []


def test_seats_in_play_is_clamped_to_the_seats_dragncards_has():
    """A plugin may allow more players than DragnCards models seats for."""
    assert seats_in_play(9) == list(SEAT_IDS)
    assert len(seats_in_play(9)) == MAX_SEATS


def test_only_vacant_seats_within_the_count_are_claimed():
    state = {"game": {"playerInfo": {"player1": {"id": 42}}}}
    assert seats_to_claim(state, 2) == ["player2"]


def test_a_seat_held_by_someone_else_is_left_alone():
    """That occupant is a participant this service did not put there."""
    state = {"game": {"playerInfo": {"player1": {"id": 42}, "player2": {"id": 99}}}}
    assert seats_to_claim(state, 2) == []


def test_seats_beyond_the_player_count_are_not_claimed():
    state = {"game": {"playerInfo": {"player1": {"id": 42}}}}
    assert seats_to_claim(state, 2) == ["player2"]
    assert "player3" not in seats_to_claim(state, 2)


def test_seat_held_by_matches_only_the_named_seat_and_user():
    state = {"game": {"playerInfo": {"player2": {"id": 42}}}}
    assert seat_held_by(state, "player2", 42) is True
    assert seat_held_by(state, "player2", 43) is False
    assert seat_held_by(state, "player1", 42) is False
