"""The judge projection states the orchestration mode — and stays put for chat.

The chat-mode assertions here are the important ones. They pin the projection
against LITERAL expected strings captured from the code as it stood before
orchestrated mode existed, so a chat verdict recorded before this change stays
comparable with one recorded after it. A structural assertion ("the mode note is
absent") would pass while some unrelated wording drifted; a literal will not.
"""

from __future__ import annotations

import pytest

from eval_service.judge.assembly import (
    assemble_game_input,
    assemble_move_input,
    assemble_round_input,
)
from eval_service.judge.events import (
    SESSION_MODE_CHAT,
    SESSION_MODE_ORCHESTRATED,
    session_mode_of,
    span_session_mode,
)
from eval_service.judge.prompt import (
    build_game_messages,
    build_move_messages,
    build_round_messages,
)
from tests.unit.conftest import agent_event, make_event, state_event

GAME = "g1"


def _timeline(*, session_mode: str | None = None):
    """A two-round chat/orchestrated timeline: states at 1/4/6, moves at 2/3/5."""
    return [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card", session_mode=session_mode),
        agent_event(
            game_id=GAME, seq=3, action="exhaust_card", session_mode=session_mode
        ),
        state_event(game_id=GAME, seq=4, round_number=1),
        agent_event(game_id=GAME, seq=5, action="next_step", session_mode=session_mode),
        state_event(game_id=GAME, seq=6, round_number=2),
    ]


def _user(messages):
    return messages[1]["content"]


# --- chat mode reads exactly as it did before orchestrated mode existed -------
#
# Captured from the pre-change code (git HEAD before this change) for the
# timeline above. Do not regenerate these from the current implementation: their
# whole purpose is to be independent of it.

_CHAT_MOVE_PROMPT = (
    "Evaluate this single agent move (seq 3) in Round 1 (seqs 1-4).\n"
    "The move is one action of that round's play; grade it as its step of that "
    "play, not as a play in its own right.\n"
    "\n"
    "Prior game state:\n"
    '{"mode": "in progress", "roundNumber": 0}\n'
    "\n"
    "The agent's 1 move(s) EARLIER IN THIS ROUND, oldest first (context for the "
    "play this move continues; do not grade them):\n"
    '- seq 2: action="move_card" args={"card_id": "c2"} reasoning="because"\n'
    "\n"
    'Intended action: "exhaust_card"\n'
    'Action arguments: {"card_id": "c3"}\n'
    'Agent\'s stated reasoning: "because"\n'
    "\n"
    "Resulting game state:\n"
    '{"mode": "in progress", "roundNumber": 1}\n'
)

_CHAT_ROUND_PROMPT = (
    "Evaluate this whole round (Round 1, seqs 1-4) as a unit.\n"
    "\n"
    "Moves taken this round:\n"
    '- seq 2: action="move_card" args={"card_id": "c2"} reasoning="because"\n'
    '- seq 3: action="exhaust_card" args={"card_id": "c3"} reasoning="because"\n'
    "\n"
    "Game state at round close:\n"
    '{"mode": "in progress", "roundNumber": 1}\n'
)

_CHAT_ROUND_FOR_PLAYER_PROMPT = (
    "Evaluate this whole round for player1 (Round 1, seqs 1-4) as a unit.\n"
    "\n"
    "Moves taken this round for player1:\n"
    '- seq 2: action="move_card" args={"card_id": "c2"} reasoning="because"\n'
    '- seq 3: action="exhaust_card" args={"card_id": "c3"} reasoning="because"\n'
    "\n"
    "Game state at round close:\n"
    '{"mode": "in progress", "roundNumber": 1}\n'
)

_CHAT_GAME_PROMPT = (
    "Evaluate this whole game for player1 (seqs 1-6) as a unit, judging how well "
    "this player played across the whole game.\n"
    "\n"
    "Final game state:\n"
    '{"mode": "in progress", "roundNumber": 2}\n'
)


def test_chat_move_prompt_is_byte_identical_to_the_pre_orchestration_prompt():
    events = _timeline()
    move = assemble_move_input(events, 3, context_before=5, context_after=5)

    assert _user(build_move_messages(move)) == _CHAT_MOVE_PROMPT


def test_chat_round_prompt_is_byte_identical_to_the_pre_orchestration_prompt():
    events = _timeline()

    aggregate = assemble_round_input(events, 4)
    assert _user(build_round_messages(aggregate)) == _CHAT_ROUND_PROMPT

    for_player = assemble_round_input(events, 4, player="player1")
    assert _user(build_round_messages(for_player)) == _CHAT_ROUND_FOR_PLAYER_PROMPT


def test_chat_game_prompt_is_byte_identical_to_the_pre_orchestration_prompt():
    events = _timeline()
    game = assemble_game_input(events, 6, from_seq=1, player="player1")

    assert _user(build_game_messages(game)) == _CHAT_GAME_PROMPT


def test_the_chat_prompts_carry_no_mode_wording_at_all():
    """Not merely "the mode is chat" — the word must not appear."""
    events = _timeline()
    rendered = "".join(
        (
            _user(build_move_messages(assemble_move_input(events, 3))),
            _user(build_round_messages(assemble_round_input(events, 4))),
            _user(
                build_game_messages(
                    assemble_game_input(events, 6, from_seq=1, player="player1")
                )
            ),
        )
    ).lower()

    assert "orchestrated" not in rendered
    assert "session_mode" not in rendered
    assert "separate agent" not in rendered


# --- orchestrated mode is stated, with the separate-context caveat -----------


@pytest.mark.parametrize("scope", ["move", "round", "game"])
def test_an_orchestrated_projection_states_the_mode_and_separate_seat_contexts(scope):
    events = _timeline(session_mode=SESSION_MODE_ORCHESTRATED)
    if scope == "move":
        rendered = _user(build_move_messages(assemble_move_input(events, 3)))
    elif scope == "round":
        rendered = _user(build_round_messages(assemble_round_input(events, 4)))
    else:
        rendered = _user(
            build_game_messages(
                assemble_game_input(events, 6, from_seq=1, player="player1")
            )
        )

    assert "ORCHESTRATED mode" in rendered
    # The caveat the requirement exists for: a seat must not be marked down for
    # information it had no way of holding.
    assert "SEPARATE agent" in rendered
    assert "its own conversation context" in rendered
    assert "its own persona" in rendered
    assert "could not have seen" in rendered


def test_the_mode_note_precedes_the_instruction_it_qualifies():
    events = _timeline(session_mode=SESSION_MODE_ORCHESTRATED)
    rendered = _user(build_round_messages(assemble_round_input(events, 4)))

    assert rendered.index("ORCHESTRATED mode") < rendered.index(
        "Evaluate this whole round"
    )


# --- reading the mode off the events ----------------------------------------


def test_an_event_with_no_recorded_mode_reads_as_chat():
    events = _timeline()

    assert session_mode_of(events[1]) == SESSION_MODE_CHAT
    assert assemble_move_input(events, 3).session_mode == SESSION_MODE_CHAT
    assert assemble_round_input(events, 4).session_mode == SESSION_MODE_CHAT


def test_an_unrecognised_recorded_mode_reads_as_chat():
    """A value from a future producer is not projected as if it were understood."""
    event = make_event(
        game_id=GAME,
        seq=2,
        actor="agent",
        event_type="agent_move",
        payload={"intended_action": "play", "session_mode": "swarm"},
    )

    assert session_mode_of(event) == SESSION_MODE_CHAT


def test_the_round_and_game_inputs_read_the_mode_from_the_span():
    events = _timeline(session_mode=SESSION_MODE_ORCHESTRATED)

    assert assemble_move_input(events, 3).session_mode == SESSION_MODE_ORCHESTRATED
    assert assemble_round_input(events, 4).session_mode == SESSION_MODE_ORCHESTRATED
    assert (
        assemble_game_input(events, 6, from_seq=1, player="player1").session_mode
        == SESSION_MODE_ORCHESTRATED
    )


def test_the_span_mode_ignores_events_outside_it():
    """Round 2 is orchestrated; round 1's projection must not inherit that."""
    events = [
        state_event(game_id=GAME, seq=1, round_number=0),
        agent_event(game_id=GAME, seq=2, action="move_card"),
        state_event(game_id=GAME, seq=3, round_number=1),
        agent_event(
            game_id=GAME,
            seq=4,
            action="next_step",
            session_mode=SESSION_MODE_ORCHESTRATED,
        ),
        state_event(game_id=GAME, seq=5, round_number=2),
    ]

    assert span_session_mode(events, 1, 3) == SESSION_MODE_CHAT
    assert span_session_mode(events, 4, 5) == SESSION_MODE_ORCHESTRATED
    assert assemble_round_input(events, 3).session_mode == SESSION_MODE_CHAT


def test_the_orchestrators_own_seatless_event_still_reads_as_orchestrated():
    """The mode must be readable without inferring it from a seat identifier.

    An orchestrated event with no ``player`` is the coordinating agent's own
    bookkeeping. Reading a missing seat as evidence of chat mode is exactly the
    inference the requirement forbids.
    """
    coordinator_move = agent_event(
        game_id=GAME,
        seq=2,
        action="villain_encounter_phase",
        session_mode=SESSION_MODE_ORCHESTRATED,
    )

    assert "player" not in coordinator_move.payload
    assert session_mode_of(coordinator_move) == SESSION_MODE_ORCHESTRATED
