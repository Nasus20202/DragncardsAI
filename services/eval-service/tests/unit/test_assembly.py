from __future__ import annotations

import pytest

from eval_service.judge.assembly import (
    BoundaryUndetectedError,
    assemble_move_input,
    assemble_round_input,
    detect_round_boundaries,
    round_number_of,
    round_of_play,
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
    # The state at seq5 is the POST-action state of the move that closed the
    # round, so the round ends AT seq5 and the next one starts at seq6. Rounds
    # are numbered as rounds of play (raw roundNumber + 1), so raw 1 is round 2.
    assert (2, 1, 5) in boundaries
    assert boundaries[-1] == (3, 6, 7)


def test_round_boundary_terminal_fallback_closes_final_round():
    # No round-number change, only a terminal status closes the round.
    events = [
        state_event(game_id="g2", seq=1, round_number=1),
        agent_event(game_id="g2", seq=2),
        state_event(game_id="g2", seq=3, round_number=1, status="loss"),
    ]
    boundaries = detect_round_boundaries(events)
    assert boundaries == [(2, 1, 3)]


def test_round_change_and_terminal_on_the_same_event_closes_once():
    # The event that closes the round is also the terminal one. It must close the
    # round exactly once, and must NOT also open an empty round after itself.
    events = [
        state_event(game_id="g2b", seq=1, round_number=0),
        agent_event(game_id="g2b", seq=2, action="next_step"),
        state_event(game_id="g2b", seq=3, round_number=1, status="win"),
    ]
    assert detect_round_boundaries(events) == [(1, 1, 3)]


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
    rnd = assemble_round_input(events, closing_seq=5)
    assert rnd.round_number == 2
    assert (rnd.from_seq, rnd.to_seq) == (1, 5)
    # moves within the round: seq2 and seq4
    assert [m.target_seq for m in rnd.moves] == [2, 4]


def _dra14_recorded_game(game_id="35128894-0cad-4b53-b195-d74b7428fe2c"):
    """The round-boundary shape of the real recorded game named in DRA-9/DRA-14.

    Ground truth from that game's 122 recorded events: the raw ``roundNumber`` goes
    0 -> 1 at seq 63 and 1 -> 2 at seq 103, and seq 63 is the ``next_step`` whose
    PRE-action state was still the previous round's End step -- the move that ENDED
    the first round of play. ``roundNumber`` counts completed rounds, so it reads 0
    for that whole first round.
    """
    return [
        state_event(game_id=game_id, seq=1, round_number=0),
        agent_event(game_id=game_id, seq=61, action="play_card"),
        agent_event(game_id=game_id, seq=62, action="next_step"),
        # Post-action state of the move that closed the first round of play.
        state_event(game_id=game_id, seq=63, round_number=1),
        agent_event(game_id=game_id, seq=102, action="next_step"),
        state_event(game_id=game_id, seq=103, round_number=2),
        agent_event(game_id=game_id, seq=121, action="play_card"),
        state_event(game_id=game_id, seq=122, round_number=2),
    ]


def test_round_spans_end_at_the_event_that_closed_the_round():
    # Pinned to the real seqs from the game DRA-14 was confirmed against: the
    # round-changing event closes the round it changed OUT of, so round 1 of play
    # ends at seq 63 (not seq 62) and round 2 starts at seq 64 (not seq 63).
    boundaries = detect_round_boundaries(_dra14_recorded_game())
    assert boundaries == [(1, 1, 63), (2, 64, 103), (3, 104, 122)]
    closing_seqs = [to for _rn, _frm, to in boundaries]
    # The pre-fix behaviour: rounds closed one event early, at the last seq BEFORE
    # the round-number change.
    assert 62 not in closing_seqs
    assert 102 not in closing_seqs


def test_round_numbers_are_rounds_of_play_not_the_completed_round_counter():
    # DragnCards `roundNumber` counts COMPLETED rounds, so it is 0 for the whole
    # first round of play. A judge (and a user) must be told "round 1", never
    # "round 0" -- the same convention the History UI displays.
    rounds = [rn for rn, _frm, _to in detect_round_boundaries(_dra14_recorded_game())]
    assert rounds == [1, 2, 3]
    assert round_of_play(0) == 1


def test_round_closing_move_is_graded_inside_the_round_it_closed():
    events = _dra14_recorded_game()
    first = assemble_round_input(events, closing_seq=63)
    assert first.round_number == 1
    assert (first.from_seq, first.to_seq) == (1, 63)
    # The `next_step` at seq 62 ended this round; it belongs to it, and so does the
    # play before it.
    assert [m.target_seq for m in first.moves] == [61, 62]
    # And the round's closing board is the state recorded at its closing seq -- one
    # completed round -- not the state from before the closing action.
    assert first.closing_state is not None
    assert first.closing_state["roundNumber"] == 1

    second = assemble_round_input(events, closing_seq=103)
    assert second.round_number == 2
    assert (second.from_seq, second.to_seq) == (64, 103)
    assert [m.target_seq for m in second.moves] == [102]


def test_round_number_of_reads_raw_game_shape():
    raw_state = make_event(
        game_id="g4",
        seq=1,
        actor="game-service",
        payload={"state": {"game": {"roundNumber": 5}}},
    )
    assert round_number_of(raw_state) == 5


def test_move_context_is_scoped_to_the_moves_round():
    # seq4 is the last agent move of the first round (span 1-5, closing at the
    # seq-5 state event that first reported the new round -- the event that CLOSED
    # this round); seq6 belongs to the next round. A generous backstop must NOT
    # pull seq6 in: an adjacent round is a different turn on a different board, and
    # grading a move against it is exactly the inaccuracy DRA-10 fixes.
    events = _recorded_game()
    move = assemble_move_input(
        events, target_seq=4, context_before=50, context_after=50
    )
    # Round of play 2 (raw DragnCards roundNumber 1).
    assert move.round_number == 2
    assert move.round_span == (1, 5)
    assert [n.seq for n in move.context_before] == [2]
    assert [n.seq for n in move.context_after] == []
    assert move.context_before[0].intended_action == "play_a"


def test_move_context_includes_the_following_moves_of_the_round():
    # The reporter's "attach not only previous moves, but also the following
    # ones": the FIRST move of a round must still see the rest of that round.
    events = _recorded_game()
    move = assemble_move_input(
        events, target_seq=2, context_before=50, context_after=50
    )
    assert [n.seq for n in move.context_before] == []
    assert [n.seq for n in move.context_after] == [4]
    assert move.context_after[0].intended_action == "play_b"


def test_move_context_covers_a_whole_multi_move_round_both_ways():
    # The reporter's case: one play spread across several calls inside one round.
    events = [
        state_event(game_id="g1", seq=1, round_number=0),
        agent_event(game_id="g1", seq=2, action="move_card"),
        agent_event(game_id="g1", seq=3, action="exhaust_card"),
        agent_event(game_id="g1", seq=4, action="modify_tokens"),
        agent_event(game_id="g1", seq=5, action="next_step"),
        state_event(game_id="g1", seq=6, round_number=1),
        agent_event(game_id="g1", seq=7, action="draw_card"),
    ]
    move = assemble_move_input(
        events, target_seq=3, context_before=50, context_after=50
    )
    # Round of play 1 -- raw roundNumber 0 IS the first round of play.
    assert move.round_number == 1
    assert [n.seq for n in move.context_before] == [2]
    assert [n.seq for n in move.context_after] == [4, 5]


def test_move_context_keeps_non_strategic_actions_as_context():
    # A card search is skipped as a TARGET (it cannot be a wrong decision) but it
    # still shows intent, so it stays in the context window.
    events = [
        state_event(game_id="g1", seq=1, round_number=0),
        agent_event(game_id="g1", seq=2, action="search_cards_marvel_champions"),
        agent_event(game_id="g1", seq=3, action="move_card"),
        state_event(game_id="g1", seq=4, round_number=1),
    ]
    move = assemble_move_input(
        events, target_seq=3, context_before=50, context_after=50
    )
    assert [n.intended_action for n in move.context_before] == [
        "search_cards_marvel_champions"
    ]


def test_move_input_window_defaults_to_no_neighbours():
    move = assemble_move_input(_recorded_game(), target_seq=4)
    assert move.context_before == []
    assert move.context_after == []


def test_move_context_backstop_keeps_the_nearest_moves_of_a_long_round():
    # The backstop exists only for a pathological round. When it bites it keeps
    # the moves NEAREST the graded one, which are the ones most likely to be part
    # of the same play.
    events = [state_event(game_id="g1", seq=1, round_number=0)]
    events += [agent_event(game_id="g1", seq=seq) for seq in range(2, 12)]
    events.append(state_event(game_id="g1", seq=12, round_number=1))
    move = assemble_move_input(events, target_seq=7, context_before=2, context_after=2)
    assert [n.seq for n in move.context_before] == [5, 6]
    assert [n.seq for n in move.context_after] == [8, 9]


def test_move_context_after_zero_removes_hindsight_within_the_round():
    events = _recorded_game()
    move = assemble_move_input(events, target_seq=2, context_before=50, context_after=0)
    assert [n.seq for n in move.context_after] == []


def test_move_context_falls_back_to_neighbours_with_no_detectable_round():
    # No recorded state carries a round number, so no round span contains the
    # move. Falling back to the nearest moves beats grading with no context.
    events = [
        agent_event(game_id="g9", seq=1, action="a"),
        agent_event(game_id="g9", seq=2, action="b"),
        agent_event(game_id="g9", seq=3, action="c"),
    ]
    move = assemble_move_input(events, target_seq=2, context_before=5, context_after=5)
    assert move.round_number is None
    assert move.round_span is None
    assert [n.seq for n in move.context_before] == [1]
    assert [n.seq for n in move.context_after] == [3]


def test_round_input_omits_non_strategic_moves_and_counts_them():
    events = [
        state_event(game_id="g5", seq=1, round_number=1),
        agent_event(game_id="g5", seq=2, action="search_cards_marvel_champions"),
        agent_event(game_id="g5", seq=3, action="move_card"),
        state_event(game_id="g5", seq=4, round_number=2),
    ]
    rnd = assemble_round_input(
        events,
        closing_seq=4,
        skip_actions=frozenset({"search_cards_marvel_champions"}),
    )
    assert [m.target_seq for m in rnd.moves] == [3]
    assert rnd.omitted_non_strategic == 1
    # Without a skip set the round still lists every move.
    every = assemble_round_input(events, closing_seq=4)
    assert [m.target_seq for m in every.moves] == [2, 3]
    assert every.omitted_non_strategic == 0


def test_round_closing_state_falls_back_to_the_nearest_recorded_state():
    # A still-open trailing round closes at the last recorded seq, which can be an
    # agent move and therefore carries no state of its own. Grading a round with no
    # board at all is what this guards against.
    events = [
        state_event(game_id="g6", seq=1, round_number=1),
        agent_event(game_id="g6", seq=2),
        state_event(game_id="g6", seq=3, round_number=2),
        agent_event(game_id="g6", seq=4),
    ]
    rnd = assemble_round_input(events, closing_seq=4)
    assert rnd.to_seq == 4
    assert rnd.closing_state is not None
    assert rnd.closing_state["roundNumber"] == 2
