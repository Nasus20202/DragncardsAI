"""Server-side enforcement of *when* a seat may act: turn and phase authority.

``seat_guard.py`` answers "whose cards does this call touch" and says, in its
scope note, that *when* an action happens — that a seat must not advance the
phase or play out of turn — is an orchestrator-side judgement made from game
state, not a property of the arguments. That judgement is this module: a pure
check over the tool name and the current step of the game, run at the seat's
call site after the seat guard has passed.

The check reads only the phase, never the acting player. The simplified game
state's ``stepId`` classifies the phase — player steps ``1.1``/``1.2``, villain
steps ``2.1``..``2.5``, beginning ``0.0``, end ``0.1`` — and the player phase is
the only phase in which a seat holds any authority to act or to advance the
game. *Which seat* holds the turn within the player phase is not a field
anywhere in the state (root ``AGENTS.md``: "whose turn it is is not a field
anywhere, and the orchestrating prompt tracks it"), so that slice stays the
orchestrator's prompt-tracked judgement; this module enforces what state can
prove, which is exactly the gap the orchestrator previously had to notice by
hand.

The enforcement shape is DRA-62's option 3: detect after the fact and record a
finding. The call is not refused — the seat guard's pre-dispatch gate is still
the only one — but a phase-advancing tool called outside the player phase, or an
action tool called while the villain resolves, becomes an open illegal-action
finding against the seat, carried into every later invocation of that seat until
the coordinator resolves it and handed to the judge as recorded evidence.

The function is pure: no repository, no I/O, no logging. Recording the finding
is the caller's job, exactly as ``seat_scope_violation`` events are the seat
guard's caller's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Tools that move the shared step marker. They belong to the coordinator: a seat
# that calls one outside the player phase is advancing the game when no seat
# holds the authority to do so.
PHASE_ADVANCING_TOOLS = frozenset(
    {"next_step", "prev_step", "player_end_phase", "villain_end_phase"}
)

# The game-mutating tools a seat plays with on its own turn. Called while the
# board is outside the player phase, they are a seat acting out of turn.
# `mulligan_draw_hand` is deliberately absent: it is the one action a seat
# performs during setup (round 0, outside the player phase), so including it
# would turn every game's opening into a finding. Lifecycle tools
# (`create_game`, `load_prebuilt_deck`, `set_player_count_action`, ...) and
# read-only tools (`get_game_state`, `search_cards_*`, ...) are absent for the
# same reason: they are not "playing".
SEAT_ACTION_TOOLS = frozenset(
    {
        "draw_card",
        "move_card",
        "set_card_property",
        "exhaust_card",
        "ready_card",
        "flip_card",
        "deal_encounter",
        "draw_boost",
        "shuffle_into_deck",
        "zero_tokens",
        "shadows_of_the_past",
        "villain_encounter_phase",
        "multiple_double_sided_villains",
        "discard_minion",
        "discard_side_scheme",
        "modify_tokens",
    }
)

# The step ids of the Marvel Champions phases, from the plugin's `steps.json`.
# The player phase is the only phase where a seat acts; the villain phase
# resolves; beginning and end of round belong to nobody.
PLAYER_PHASE_STEPS = frozenset({"1.1", "1.2"})
VILLAIN_PHASE_STEPS = frozenset({"2.1", "2.2", "2.3", "2.4", "2.5"})
PASSIVE_PHASE_STEPS = frozenset({"0.0", "0.1"})

PHASE_PLAYER = "player"
PHASE_VILLAIN = "villain"
PHASE_PASSIVE = "passive"
PHASE_UNKNOWN = "unknown"

VIOLATION_KIND_PHASE_ADVANCE = "phase_advance"
VIOLATION_KIND_ACTION = "action"

# The phases, named the way a seat should be able to read them back.
_PHASE_LABELS = {
    PHASE_PLAYER: "player phase",
    PHASE_VILLAIN: "villain phase",
    PHASE_PASSIVE: "between-round phase",
    PHASE_UNKNOWN: "unknown phase",
}


@dataclass(frozen=True)
class TurnAuthorityViolation:
    """A seat's tool call that no seat could make at the current step.

    ``kind`` says which rule broke: ``phase_advance`` for a phase-advancing tool
    called outside the player phase, ``action`` for an action tool called
    outside it. ``step_id`` and ``phase`` are what the state read showed, so the
    finding names the board as it was, not the board as the seat claims it was.
    """

    caller_player_id: str
    tool_name: str
    step_id: str | None
    phase: str
    kind: str

    @property
    def message(self) -> str:
        """The violation text recorded against the seat, written to be read."""
        phase_label = _PHASE_LABELS.get(self.phase, self.phase)
        step = f" (step {self.step_id})" if self.step_id is not None else ""
        if self.kind == VIOLATION_KIND_PHASE_ADVANCE:
            return (
                f"Advanced the game by calling `{self.tool_name}` while the "
                f"board is in the {phase_label}{step}, when only the player "
                f"phase is a seat's to advance. Phase advancement belongs to "
                f"the coordinator."
            )
        return (
            f"Acted out of turn: called `{self.tool_name}` while the board is "
            f"in the {phase_label}{step}, when a seat may only act during the "
            f"player phase."
        )

    @property
    def required_undo(self) -> str:
        """The concrete repair the seat is expected to perform, if any."""
        if self.kind == VIOLATION_KIND_PHASE_ADVANCE:
            return (
                "Do not advance the phase again. The step marker has moved; "
                "read the board and report what changed so the coordinator can "
                "decide whether to restore the previous step."
            )
        return (
            "Undo whatever this call changed, with your own tools, or say in "
            "your report exactly what the board shows now and what it showed "
            "before, so the coordinator can repair it. Take no further "
            "game-changing action until your turn."
        )


def check_turn_authority(
    *,
    caller_player_id: str,
    tool_name: str,
    step_id: Any,
) -> TurnAuthorityViolation | None:
    """The turn-authority violation this call commits, or ``None``.

    ``step_id`` is the current step from the simplified game state (the
    ``state.stepId`` of ``get_game_state``); ``tool_name`` is the *actual*
    game-service tool name, without the registry prefix. Only the phase
    classifies the call: an unknown or missing step id proves nothing and never
    fires, so a board that cannot be read does not manufacture findings.
    """
    if tool_name not in PHASE_ADVANCING_TOOLS and tool_name not in SEAT_ACTION_TOOLS:
        return None
    phase = phase_of(step_id)
    if phase in (PHASE_PLAYER, PHASE_UNKNOWN):
        return None
    return TurnAuthorityViolation(
        caller_player_id=caller_player_id,
        tool_name=tool_name,
        step_id=None if step_id is None else str(step_id),
        phase=phase,
        kind=(
            VIOLATION_KIND_PHASE_ADVANCE
            if tool_name in PHASE_ADVANCING_TOOLS
            else VIOLATION_KIND_ACTION
        ),
    )


def phase_of(step_id: Any) -> str:
    """The phase the step id belongs to, or ``unknown``.

    The raw engine writes the step id both as a string (``"1.1"``) and as an
    integer (``0`` during setup), so the comparison is on the normalized string
    and anything unrecognized — including the integer ``0`` — is ``unknown``.
    """
    if step_id is None:
        return PHASE_UNKNOWN
    step = str(step_id)
    if step in PLAYER_PHASE_STEPS:
        return PHASE_PLAYER
    if step in VILLAIN_PHASE_STEPS:
        return PHASE_VILLAIN
    if step in PASSIVE_PHASE_STEPS:
        return PHASE_PASSIVE
    return PHASE_UNKNOWN
