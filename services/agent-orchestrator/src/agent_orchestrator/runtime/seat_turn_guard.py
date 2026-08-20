"""Server-side enforcement of *when* a seat may act: turn and phase authority.

``seat_guard.py`` answers "whose cards does this call touch" and says, in its
scope note, that *when* an action happens — that a seat must not advance the
phase or play out of turn — is an orchestrator-side judgement made from game
state, not a property of the arguments. That judgement is this module: a pure
check over the tool name and the current step of the game, run at the seat's
call site after the seat guard has passed.

The check reads the neutral phase classification, never a platform's own step
identifier. The player phase is the only phase in which a seat holds authority
to act or to advance the game. On a platform that reports pending decisions,
the pending-seat set is an additional source of turn authority. *Which seat*
holds the turn on a platform that does not report it remains the orchestrator's
prompt-tracked judgement; this module enforces what state can prove.

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

from agent_orchestrator.runtime.platforms import (
    DEFAULT_PLATFORM,
    PLATFORM_DRAGNCARDS,
    platform_tool_sets,
)

# Backwards-compatible DragnCards exports. Runtime callers resolve these sets
# through ``platform_tool_sets`` so one platform cannot classify another's
# tools.
PHASE_ADVANCING_TOOLS = platform_tool_sets(PLATFORM_DRAGNCARDS).phase_advancing
SEAT_ACTION_TOOLS = platform_tool_sets(PLATFORM_DRAGNCARDS).seat_actions

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
    phase_label: str | None = None
    pending_seats: tuple[str, ...] | None = None

    @property
    def message(self) -> str:
        """The violation text recorded against the seat, written to be read."""
        if self.pending_seats is not None and self.kind == VIOLATION_KIND_ACTION:
            pending = ", ".join(self.pending_seats) or "no seat"
            phase_label = self.phase_label or _PHASE_LABELS.get(self.phase, self.phase)
            return (
                f"Acted while the platform was not asking seat "
                f"{self.caller_player_id}: called `{self.tool_name}` during "
                f"{phase_label}, but the pending decision belongs to {pending}."
            )
        phase_label = self.phase_label or _PHASE_LABELS.get(self.phase, self.phase)
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
    step_id: Any = None,
    phase: Any = None,
    phase_label: str | None = None,
    pending_seats: Any = None,
    platform: Any = DEFAULT_PLATFORM,
) -> TurnAuthorityViolation | None:
    """The turn-authority violation this call commits, or ``None``.

    ``phase`` is the neutral classification from the simplified game state and
    ``step_id`` is retained only as an opaque value for the finding text.
    ``tool_name`` is the *actual* game-service tool name, without the registry
    prefix. An unknown or missing classification proves nothing and never fires,
    so a board that cannot be read does not manufacture findings. When
    ``pending_seats`` is supplied, it is authoritative for seat-action tools;
    the phase classification is only the fallback when that field is omitted.
    """
    tool_sets = platform_tool_sets(platform)
    if (
        tool_name not in tool_sets.phase_advancing
        and tool_name not in tool_sets.seat_actions
    ):
        return None
    resolved_phase = phase if isinstance(phase, str) else PHASE_UNKNOWN
    if resolved_phase not in {
        PHASE_PLAYER,
        PHASE_VILLAIN,
        PHASE_PASSIVE,
        "setup",
        PHASE_UNKNOWN,
    }:
        resolved_phase = PHASE_UNKNOWN
    normalized_pending = _normalize_pending_seats(pending_seats)
    if (
        normalized_pending is not None
        and tool_name in tool_sets.seat_actions
        and caller_player_id.strip().lower() not in normalized_pending
    ):
        return TurnAuthorityViolation(
            caller_player_id=caller_player_id,
            tool_name=tool_name,
            step_id=None if step_id is None else str(step_id),
            phase=resolved_phase,
            kind=VIOLATION_KIND_ACTION,
            phase_label=phase_label,
            pending_seats=normalized_pending,
        )
    # A platform-provided pending decision is stronger than the broad phase
    # label. A named seat may submit its legal option during setup, passive, or
    # any other phase label while the prompt is pending.
    if normalized_pending is not None and tool_name in tool_sets.seat_actions:
        return None
    if resolved_phase == PHASE_UNKNOWN:
        return None
    if resolved_phase == PHASE_PLAYER:
        return None
    return TurnAuthorityViolation(
        caller_player_id=caller_player_id,
        tool_name=tool_name,
        step_id=None if step_id is None else str(step_id),
        phase=resolved_phase,
        kind=(
            VIOLATION_KIND_PHASE_ADVANCE
            if tool_name in tool_sets.phase_advancing
            else VIOLATION_KIND_ACTION
        ),
        phase_label=phase_label,
        pending_seats=normalized_pending,
    )


def _normalize_pending_seats(value: Any) -> tuple[str, ...] | None:
    if value is None or not isinstance(value, (list, tuple, set, frozenset)):
        return None
    return tuple(
        sorted(
            {
                item.strip().lower()
                for item in value
                if isinstance(item, str) and item.strip()
            }
        )
    )
