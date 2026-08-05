"""Illegal-action findings: evidence for the judge, and never mistaken for a move.

Two separable concerns, and the first is the dangerous one.

An ``illegal_action`` finding is an ``agent`` event, because history-service pins
``actor`` to a fixed literal set and a new orchestrator concern therefore arrives
as a new event type under an existing actor. Every place that identified a move by
``actor == "agent"`` alone would have picked the finding up as a move: graded it as
a play, attributed it to a seat as that seat's action, counted it into a round's
move total, and — since a round's span and its closing state are read against its
events — been able to move a round boundary. The tests here hold that line at each
of those points, not just at the grading one.
"""

from __future__ import annotations

import pytest

from eval_service.judge.assembly import (
    assemble_game_input,
    assemble_move_input,
    assemble_round_input,
    collect_illegal_actions,
    detect_round_boundaries,
)
from eval_service.judge.events import is_agent_move, is_illegal_action_finding
from eval_service.judge.prompt import build_round_messages
from eval_service.judge.rounds import neighbour_events
from eval_service.runtime.players import attribute_move, players_in_span
from eval_service.runtime.rounds import _summarize
from tests.unit.conftest import (
    agent_event,
    illegal_action_event,
    make_event,
    state_event,
)

GAME = "g1"


def _timeline_with_a_finding():
    """Round 1 = seqs 1-5, with an ``illegal_action`` finding sitting at seq 4.

    The finding is deliberately placed BETWEEN two moves and inside the round, so
    that treating it as a move would be visible in the move list, in the move
    index used for seat attribution, and in the neighbour window.
    """
    return [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        agent_event(game_id=GAME, seq=3, action="exhaust_card"),
        illegal_action_event(
            game_id=GAME,
            seq=4,
            player="player1",
            violation="attacked with an exhausted hero",
        ),
        agent_event(game_id=GAME, seq=5, action="next_step"),
        state_event(game_id=GAME, seq=6, round_number=1),
    ]


def _no_finding_timeline():
    """The same timeline with the finding removed, for a like-for-like comparison."""
    return [e for e in _timeline_with_a_finding() if e.seq != 4]


def _user(messages):
    return messages[1]["content"]


# --- the trap: a finding is not a move ---------------------------------------


def test_the_predicate_separates_a_finding_from_a_move():
    events = _timeline_with_a_finding()
    finding = next(e for e in events if e.seq == 4)
    move = next(e for e in events if e.seq == 2)

    assert finding.actor == "agent", "a finding rides on the agent actor"
    assert is_illegal_action_finding(finding)
    assert not is_agent_move(finding)
    assert is_agent_move(move)


def test_a_finding_is_not_graded_as_a_move():
    events = _timeline_with_a_finding()

    with pytest.raises(ValueError, match="expected an agent move"):
        assemble_move_input(events, 4)


def test_a_finding_is_not_listed_among_a_rounds_moves():
    rnd = assemble_round_input(_timeline_with_a_finding(), 6)

    assert [move.target_seq for move in rnd.moves] == [2, 3, 5]
    assert 4 not in [move.target_seq for move in rnd.moves]


def test_a_finding_is_not_counted_in_a_rounds_move_total():
    events = _timeline_with_a_finding()
    round_of_play, from_seq, to_seq = detect_round_boundaries(events)[0]

    summary = _summarize(events, round_of_play, from_seq, to_seq)

    assert summary.move_count == 3


def test_a_finding_is_not_attributed_to_a_player_as_a_move():
    """The finding names ``player1``, but that must not make it player1's *move*.

    Seat attribution walks a round's moves in turn order, so a finding counted as
    a move would also shift every later move onto the wrong seat.
    """
    events = [
        make_event(
            game_id=GAME,
            seq=1,
            actor="game-service",
            event_type="game_state",
            payload={
                "state": {
                    "game": {
                        "roundNumber": 0,
                        "numPlayers": 2,
                        "firstPlayer": "player1",
                    }
                },
                "status": "in progress",
            },
        ),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        illegal_action_event(game_id=GAME, seq=3, player="player1"),
        agent_event(game_id=GAME, seq=4, action="exhaust_card"),
    ]

    # Move index 0 -> player1, move index 1 -> player2. Had the finding at seq 3
    # been counted, seq 4 would have landed on index 2 and wrapped to player1.
    assert attribute_move(events, 2) == "player1"
    assert attribute_move(events, 4) == "player2"


def test_a_finding_does_not_shift_a_round_boundary_or_span():
    with_finding = detect_round_boundaries(_timeline_with_a_finding())
    without_finding = detect_round_boundaries(_no_finding_timeline())

    assert with_finding == without_finding

    rnd_with = assemble_round_input(_timeline_with_a_finding(), 6)
    rnd_without = assemble_round_input(_no_finding_timeline(), 6)
    assert (rnd_with.from_seq, rnd_with.to_seq) == (
        rnd_without.from_seq,
        rnd_without.to_seq,
    )
    assert rnd_with.closing_state == rnd_without.closing_state


def test_a_trailing_finding_joins_the_open_round_instead_of_starting_a_new_one():
    """The one span a trailing event does move, and why that is the right answer.

    A still-open trailing round closes at the timeline's LAST seq, whatever event
    that is — which has always been true of any trailing non-state event, a
    ``user_prompt`` included. So a finding recorded straight after the round's last
    move extends that round's span to cover it, exactly as a trailing prompt does.

    That is the behaviour to want: the finding belongs to the round it was recorded
    in, and a span that stopped short of it would put the evidence outside the
    round it is evidence about. What must not happen — and does not — is a phantom
    extra round, or a closed round moving.
    """
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        state_event(game_id=GAME, seq=3, round_number=1),
        agent_event(game_id=GAME, seq=4, action="exhaust_card"),
    ]
    trailing_finding = illegal_action_event(game_id=GAME, seq=5, player="player1")

    before = detect_round_boundaries(events)
    after = detect_round_boundaries([*events, trailing_finding])

    assert len(after) == len(before), "no phantom round is created"
    assert after[0] == before[0], "the closed round is untouched"
    assert after[-1] == (2, 4, 5), "the open round grows to cover the finding"

    rnd = assemble_round_input([*events, trailing_finding], 5)
    assert [move.target_seq for move in rnd.moves] == [4]
    assert [f.seq for f in rnd.illegal_actions] == [5]


def test_a_finding_is_not_offered_as_neighbour_context_for_a_move():
    events = _timeline_with_a_finding()

    after = neighbour_events(events, 3, direction="after", limit=5, span=(1, 6))

    assert [event.seq for event in after] == [5]


def test_a_finding_does_not_make_a_seat_look_like_it_acted():
    """A round in which only a finding mentions a seat has no move by that seat."""
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        illegal_action_event(game_id=GAME, seq=2, player="player2"),
        state_event(game_id=GAME, seq=3, round_number=1),
    ]

    # No agent MOVE in the span, so the span collapses to the single-player
    # default rather than reporting player2 as having played.
    assert players_in_span(events, 1, 3) == ["player1"]


def test_a_finding_is_not_a_game_roll_ups_move_either():
    events = _timeline_with_a_finding()

    game = assemble_game_input(events, 6, from_seq=1, player="player1")

    assert game.to_seq == 6


# --- the evidence itself -----------------------------------------------------


def test_a_recorded_violation_reaches_the_judge_naming_seat_and_violation():
    rnd = assemble_round_input(_timeline_with_a_finding(), 6)

    assert [f.seq for f in rnd.illegal_actions] == [4]
    finding = rnd.illegal_actions[0]
    assert finding.player == "player1"
    assert finding.violation == "attacked with an exhausted hero"
    assert not finding.is_resolved

    rendered = _user(build_round_messages(rnd))
    assert "player1" in rendered
    assert "attacked with an exhausted hero" in rendered


def test_a_resolved_finding_is_distinguishable_from_an_open_one():
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        illegal_action_event(
            game_id=GAME,
            seq=3,
            player="player1",
            violation="played an ally with no resources paid",
            status="resolved",
            resolution_note="seat returned the ally to hand",
        ),
        illegal_action_event(
            game_id=GAME,
            seq=4,
            player="player2",
            violation="attacked with an exhausted hero",
            status="open",
        ),
        state_event(game_id=GAME, seq=5, round_number=1),
    ]
    rnd = assemble_round_input(events, 5)

    resolved, still_open = rnd.illegal_actions
    assert resolved.is_resolved
    assert not still_open.is_resolved

    rendered = _user(build_round_messages(rnd))
    assert "played an ally with no resources paid [RESOLVED" in rendered
    assert "seat returned the ally to hand" in rendered
    assert "attacked with an exhausted hero [OPEN, not undone]" in rendered


def test_the_seat_is_read_from_either_player_or_player_id():
    """The orchestrator names the same field ``player_id`` on its job events.

    ``player`` is canonical (it is what an agent move and a verdict use), but a
    finding must not end up unattributed because the producer wrote its internal
    name instead.
    """
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        make_event(
            game_id=GAME,
            seq=2,
            actor="agent",
            event_type="illegal_action",
            payload={
                "player_id": "player3",
                "violation": "played out of turn",
                "required_undo": "undo the play",
                "status": "open",
                "session_mode": "orchestrated",
            },
        ),
        state_event(game_id=GAME, seq=3, round_number=1),
    ]

    (finding,) = collect_illegal_actions(events, 1, 3)

    assert finding.player == "player3"


def test_a_finding_with_no_seat_is_still_shown_as_evidence():
    """The violation is the evidence; a missing seat is not worth losing it over."""
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        make_event(
            game_id=GAME,
            seq=2,
            actor="agent",
            event_type="illegal_action",
            payload={"violation": "played out of turn", "status": "open"},
        ),
        state_event(game_id=GAME, seq=3, round_number=1),
    ]
    rnd = assemble_round_input(events, 3)

    (finding,) = rnd.illegal_actions
    assert finding.player is None
    assert "an unnamed seat: played out of turn" in _user(build_round_messages(rnd))


def test_an_unrecognised_status_is_read_as_open_rather_than_resolved():
    """The conservative direction: an unfamiliar state must not retire a finding."""
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        illegal_action_event(game_id=GAME, seq=2, status="under-review"),
        state_event(game_id=GAME, seq=3, round_number=1),
    ]

    findings = collect_illegal_actions(events, 1, 3)

    assert len(findings) == 1
    assert not findings[0].is_resolved


def test_a_finding_with_no_named_violation_is_dropped():
    """An unnamed violation invites the judge to go looking for a fault to match."""
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        illegal_action_event(game_id=GAME, seq=2, violation="   "),
        state_event(game_id=GAME, seq=3, round_number=1),
    ]

    assert collect_illegal_actions(events, 1, 3) == []


def test_findings_outside_the_round_are_not_attached_to_it():
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        state_event(game_id=GAME, seq=3, round_number=1),
        illegal_action_event(game_id=GAME, seq=4, player="player2"),
        state_event(game_id=GAME, seq=5, round_number=2),
    ]

    first_round = assemble_round_input(events, 3)
    second_round = assemble_round_input(events, 5)

    assert first_round.illegal_actions == []
    assert [f.seq for f in second_round.illegal_actions] == [4]


def test_the_finding_is_presented_as_evidence_and_not_as_a_verdict():
    rnd = assemble_round_input(_timeline_with_a_finding(), 6)

    rendered = _user(build_round_messages(rnd))

    assert "EVIDENCE, not a verdict" in rendered
    assert "rather than letting it settle the score by itself" in rendered


def test_a_per_player_round_says_another_seats_finding_is_not_this_seats_to_answer():
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        illegal_action_event(game_id=GAME, seq=3, player="player2"),
        state_event(game_id=GAME, seq=4, round_number=1),
    ]

    rnd = assemble_round_input(events, 4, player="player1")
    rendered = _user(build_round_messages(rnd))

    # The finding is still shown -- it explains the position the round produced --
    # but it is explicitly not charged to the seat being scored.
    assert "player2" in rendered
    assert "not player1's play to answer for" in rendered


def test_a_round_with_no_findings_renders_no_evidence_block():
    rnd = assemble_round_input(_no_finding_timeline(), 6)

    rendered = _user(build_round_messages(rnd))

    assert rnd.illegal_actions == []
    assert "EVIDENCE" not in rendered
