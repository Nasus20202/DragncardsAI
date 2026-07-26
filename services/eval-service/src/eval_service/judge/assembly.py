from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eval_service.schemas.history import StoredEvent


class BoundaryUndetectedError(Exception):
    """Raised when a round boundary cannot be determined from recorded state.

    Surfaced (rather than guessing a span) so a wrong-span verdict is never
    emitted, per the design's round-boundary risk mitigation.
    """


@dataclass
class MoveInput:
    """Assembled judge input for a single move."""

    game_id: str
    target_seq: int
    intended_action: Any
    reasoning: Any
    arguments: Any
    prior_state: dict[str, Any] | None
    resulting_state: dict[str, Any] | None


@dataclass
class RoundInput:
    """Assembled judge input for a whole round/turn."""

    game_id: str
    target_seq: int
    from_seq: int
    to_seq: int
    round_number: int | None
    moves: list[MoveInput] = field(default_factory=list)
    closing_state: dict[str, Any] | None = None
    # The player this round roll-up scores (None for legacy/aggregate rounds).
    player: str | None = None
    # Already-graded child (move) verdicts for this player, as judge context.
    child_verdicts: list["ChildVerdict"] = field(default_factory=list)


@dataclass
class GameInput:
    """Assembled judge input for a whole game, scored for one player."""

    game_id: str
    target_seq: int
    from_seq: int
    to_seq: int
    player: str | None = None
    closing_state: dict[str, Any] | None = None
    # Already-graded child (round) verdicts for this player, as judge context.
    child_verdicts: list["ChildVerdict"] = field(default_factory=list)


@dataclass
class ChildVerdict:
    """A compact view of a recorded child verdict used as roll-up context."""

    scope: str
    target_seq: int
    player: str | None
    overall_score: int
    rationale: str
    round_span: list[int] | None = None


_TERMINAL_STATUSES = ("win", "loss")


def round_number_of(event: StoredEvent) -> int | None:
    """Extract the round number from a ``game-service`` state event.

    DragnCards exposes the round under ``payload.state.game.roundNumber`` (raw)
    and the simplified game state exposes ``payload.state.roundNumber`` (flat).
    Both are checked so detection is robust to which representation was recorded.
    Returns None when no round number is present.
    """
    if event.actor != "game-service":
        return None
    state = event.payload.get("state")
    if not isinstance(state, dict):
        return None
    flat = state.get("roundNumber")
    if isinstance(flat, int):
        return flat
    game = state.get("game")
    if isinstance(game, dict):
        raw = game.get("roundNumber")
        if isinstance(raw, int):
            return raw
    return None


def event_status(event: StoredEvent) -> str | None:
    status = event.payload.get("status")
    if isinstance(status, str) and status:
        return status
    return None


def is_terminal(event: StoredEvent) -> bool:
    status = event_status(event)
    return status in _TERMINAL_STATUSES if status else False


def assemble_move_input(events: list[StoredEvent], target_seq: int) -> MoveInput:
    """Assemble a per-move judge input for the ``agent`` event at ``target_seq``.

    Correlates the nearest ``game-service`` state at-or-before (prior state) and
    at-or-after (resulting state) the move's seq so the judge sees before/after.
    """
    target = _find_event(events, target_seq)
    if target is None:
        raise ValueError(f"no event at seq {target_seq}")
    if target.actor != "agent":
        raise ValueError(
            f"seq {target_seq} is actor {target.actor!r}, expected an agent move"
        )

    payload = target.payload
    prior = _nearest_state(events, target_seq, direction="before")
    resulting = _nearest_state(events, target_seq, direction="after")
    return MoveInput(
        game_id=target.game_id,
        target_seq=target_seq,
        intended_action=payload.get("intended_action"),
        reasoning=payload.get("reasoning"),
        arguments=payload.get("arguments"),
        prior_state=prior.payload.get("state") if prior else None,
        resulting_state=resulting.payload.get("state") if resulting else None,
    )


def detect_round_boundaries(events: list[StoredEvent]) -> list[tuple[int, int, int]]:
    """Return ``(round_number, from_seq, to_seq)`` for each closed round.

    A round closes when the round number changes between consecutive
    ``game-service`` state events, or at a terminal status. ``from_seq`` is the
    first event seq of the round; ``to_seq`` (the closing seq) is the last seq
    of the round (the state event that still belongs to the round). Rounds with
    no detectable round number do not contribute boundaries.
    """
    ordered = sorted(events, key=lambda e: e.seq)
    if not ordered:
        return []

    boundaries: list[tuple[int, int, int]] = []
    current_round: int | None = None
    round_start_seq = ordered[0].seq
    last_seq_in_round = ordered[0].seq

    for event in ordered:
        rn = round_number_of(event)
        if rn is not None:
            if current_round is None:
                current_round = rn
                round_start_seq = ordered[0].seq
            elif rn != current_round:
                # The previous round closed at the last seq before this change.
                boundaries.append((current_round, round_start_seq, last_seq_in_round))
                current_round = rn
                round_start_seq = last_seq_in_round + 1
        last_seq_in_round = event.seq
        if is_terminal(event):
            # Terminal status closes the final round at this event.
            close_round = current_round if current_round is not None else 0
            boundaries.append((close_round, round_start_seq, event.seq))
            return boundaries

    # No terminal status reached: close the trailing open round at the last seq
    # if a round was ever detected.
    if current_round is not None and (
        not boundaries or boundaries[-1][2] < last_seq_in_round
    ):
        boundaries.append((current_round, round_start_seq, last_seq_in_round))
    return boundaries


def assemble_round_input(
    events: list[StoredEvent], closing_seq: int, *, player: str | None = None
) -> RoundInput:
    """Assemble a per-round judge input for the round closing at ``closing_seq``.

    When ``player`` is given the round is scored for that player only: just that
    player's moves are included and the already-graded move verdicts for that
    player are attached as roll-up context. ``player=None`` preserves the legacy
    whole-round aggregate behavior.

    Raises :class:`BoundaryUndetectedError` when ``closing_seq`` is not a
    detected round-closing seq.
    """
    boundaries = detect_round_boundaries(events)
    match = next((b for b in boundaries if b[2] == closing_seq), None)
    if match is None:
        raise BoundaryUndetectedError(
            f"seq {closing_seq} is not a detected round-closing boundary"
        )
    round_number, from_seq, to_seq = match

    moves: list[MoveInput] = []
    for event in events:
        if event.actor == "agent" and from_seq <= event.seq <= to_seq:
            if player is not None and _move_player(events, event.seq) != player:
                continue
            moves.append(assemble_move_input(events, event.seq))

    closing_event = _find_event(events, closing_seq)
    closing_state = (
        closing_event.payload.get("state")
        if closing_event is not None and closing_event.actor == "game-service"
        else None
    )
    child_verdicts = (
        collect_child_verdicts(
            events, from_seq, to_seq, child_scope="move", player=player
        )
        if player is not None
        else []
    )
    return RoundInput(
        game_id=events[0].game_id if events else "",
        target_seq=closing_seq,
        from_seq=from_seq,
        to_seq=to_seq,
        round_number=round_number,
        moves=moves,
        closing_state=closing_state,
        player=player,
        child_verdicts=child_verdicts,
    )


def assemble_game_input(
    events: list[StoredEvent],
    closing_seq: int,
    *,
    from_seq: int,
    player: str | None = None,
) -> GameInput:
    """Assemble a per-game judge input scored for one player.

    The game roll-up grades holistically given the player's already-graded round
    verdicts as context. The span ``[from_seq, closing_seq]`` is the whole game.
    """
    closing_event = _find_event(events, closing_seq)
    closing_state = (
        closing_event.payload.get("state")
        if closing_event is not None and closing_event.actor == "game-service"
        else None
    )
    child_verdicts = collect_child_verdicts(
        events, from_seq, closing_seq, child_scope="round", player=player
    )
    return GameInput(
        game_id=events[0].game_id if events else "",
        target_seq=closing_seq,
        from_seq=from_seq,
        to_seq=closing_seq,
        player=player,
        closing_state=closing_state,
        child_verdicts=child_verdicts,
    )


def _move_player(events: list[StoredEvent], seq: int) -> str:
    # Lazy import to avoid a cycle with ``runtime.players`` (which imports the
    # round-boundary detection from this module).
    from eval_service.runtime.players import attribute_move

    return attribute_move(events, seq)


def collect_child_verdicts(
    events: list[StoredEvent],
    from_seq: int,
    to_seq: int,
    *,
    child_scope: str,
    player: str | None,
) -> list[ChildVerdict]:
    """Gather recorded child verdicts (evaluator events) for a roll-up's context.

    Reads the ``evaluator`` history events within ``[from_seq, to_seq]`` at
    ``child_scope`` (``move`` for a round roll-up, ``round`` for a game roll-up)
    that pertain to ``player``. Verdicts are derived purely from recorded
    history, so no in-memory dependency state is kept. Ordered by target seq.
    """
    out: list[ChildVerdict] = []
    for event in events:
        if event.actor != "evaluator" or event.event_type != "evaluation":
            continue
        payload = event.payload
        if payload.get("scope") != child_scope:
            continue
        target_seq = payload.get("target_seq")
        if not isinstance(target_seq, int) or not (from_seq <= target_seq <= to_seq):
            continue
        if player is not None and payload.get("player") not in (player, None):
            # A child verdict tagged with a DIFFERENT player is not this
            # player's; an untagged (legacy) child is included as a fallback.
            if payload.get("player") is not None:
                continue
        overall = payload.get("overall_score")
        if not isinstance(overall, int):
            continue
        round_span = payload.get("round_span")
        out.append(
            ChildVerdict(
                scope=str(payload.get("scope")),
                target_seq=target_seq,
                player=payload.get("player"),
                overall_score=overall,
                rationale=str(payload.get("rationale") or ""),
                round_span=round_span if isinstance(round_span, list) else None,
            )
        )
    out.sort(key=lambda c: c.target_seq)
    return out


def _find_event(events: list[StoredEvent], seq: int) -> StoredEvent | None:
    for event in events:
        if event.seq == seq:
            return event
    return None


def _nearest_state(
    events: list[StoredEvent], target_seq: int, *, direction: str
) -> StoredEvent | None:
    candidates = [e for e in events if e.actor == "game-service"]
    if direction == "before":
        before = [e for e in candidates if e.seq <= target_seq]
        return max(before, key=lambda e: e.seq) if before else None
    after = [e for e in candidates if e.seq >= target_seq]
    return min(after, key=lambda e: e.seq) if after else None
