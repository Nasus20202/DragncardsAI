from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from eval_service.judge.actions import non_strategic_reason
from eval_service.schemas.history import StoredEvent


class BoundaryUndetectedError(Exception):
    """Raised when a round boundary cannot be determined from recorded state.

    Surfaced (rather than guessing a span) so a wrong-span verdict is never
    emitted, per the design's round-boundary risk mitigation.
    """


@dataclass
class NeighbourMove:
    """A compact view of an agent move neighbouring the one being judged."""

    seq: int
    intended_action: Any
    arguments: Any
    reasoning: Any


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
    # A window of the agent's own neighbouring moves, so the judge can see the
    # sequence a move belongs to without being handed the whole game history.
    context_before: list["NeighbourMove"] = field(default_factory=list)
    context_after: list["NeighbourMove"] = field(default_factory=list)


@dataclass
class RoundInput:
    """Assembled judge input for a whole round/turn."""

    game_id: str
    target_seq: int
    from_seq: int
    to_seq: int
    # The 1-based round of PLAY (raw DragnCards ``roundNumber`` + 1), matching
    # what the History UI shows -- see ``round_of_play``.
    round_number: int | None
    moves: list[MoveInput] = field(default_factory=list)
    closing_state: dict[str, Any] | None = None
    # How many of the round's moves were left out as non-strategic, so the omission
    # is stated in the prompt instead of silently shrinking the round.
    omitted_non_strategic: int = 0
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
    """Extract the RAW ``roundNumber`` from a ``game-service`` state event.

    DragnCards exposes the round under ``payload.state.game.roundNumber`` (raw)
    and the simplified game state exposes ``payload.state.roundNumber`` (flat).
    Both are checked so detection is robust to which representation was recorded.
    Returns None when no round number is present.

    The value is DragnCards' own counter, which counts COMPLETED rounds — it is
    0 for the whole first round of play. Use :func:`round_of_play` before showing
    it to a judge or a user.
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


def round_of_play(raw_round_number: int) -> int:
    """The 1-based round of play for a raw DragnCards ``roundNumber``.

    ``roundNumber`` counts COMPLETED rounds (the plugin increments it as a round
    closes), so the round being played while it reads N is round ``N + 1``. This
    is the same convention the History UI displays, so a round verdict and the
    transcript name the same round.
    """
    return raw_round_number + 1


def event_status(event: StoredEvent) -> str | None:
    status = event.payload.get("status")
    if isinstance(status, str) and status:
        return status
    return None


def is_terminal(event: StoredEvent) -> bool:
    status = event_status(event)
    return status in _TERMINAL_STATUSES if status else False


def assemble_move_input(
    events: list[StoredEvent],
    target_seq: int,
    *,
    context_before: int = 0,
    context_after: int = 0,
) -> MoveInput:
    """Assemble a per-move judge input for the ``agent`` event at ``target_seq``.

    Correlates the nearest ``game-service`` state at-or-before (prior state) and
    at-or-after (resulting state) the move's seq so the judge sees before/after.

    ``context_before``/``context_after`` bound a WINDOW of the agent's own
    neighbouring moves included as context. A window rather than the whole
    history: the two correlated states already summarise everything that happened
    earlier, so replaying the full move list adds cost without adding signal,
    while the immediate neighbours carry information the states cannot — a single
    Marvel Champions play is typically 2-4 tool calls (play the card, assign
    damage, exhaust the character), and judging one of them alone invites a
    confidently wrong verdict.
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
        context_before=_neighbour_window(
            events, target_seq, count=context_before, direction="before"
        ),
        context_after=_neighbour_window(
            events, target_seq, count=context_after, direction="after"
        ),
    )


def _neighbour_window(
    events: list[StoredEvent], target_seq: int, *, count: int, direction: str
) -> list[NeighbourMove]:
    """The ``count`` agent moves nearest to ``target_seq`` on one side, in order."""
    if count <= 0:
        return []
    candidates = [
        event
        for event in events
        if event.actor == "agent"
        and (
            event.seq < target_seq if direction == "before" else event.seq > target_seq
        )
    ]
    candidates.sort(key=lambda e: e.seq)
    window = candidates[-count:] if direction == "before" else candidates[:count]
    return [
        NeighbourMove(
            seq=event.seq,
            intended_action=event.payload.get("intended_action"),
            arguments=event.payload.get("arguments"),
            reasoning=event.payload.get("reasoning"),
        )
        for event in window
    ]


def detect_round_boundaries(events: list[StoredEvent]) -> list[tuple[int, int, int]]:
    """Return ``(round_of_play, from_seq, to_seq)`` for each closed round.

    A round closes when the raw ``roundNumber`` changes between ``game-service``
    state events, or at a terminal status. ``from_seq`` is the first event seq of
    the round; ``to_seq`` (the closing seq) is the LAST seq of the round.

    A ``game-service`` event embeds the state AFTER its action was applied, so the
    event whose state first reports the NEW round number is the event that CLOSED
    the previous round: the round ends AT that event and the next round starts
    after it. Attributing it to the next round instead (as this did before) shifted
    every span by one event at each boundary and handed a round roll-up the board
    from just before its own closing action. This mirrors the History UI, which
    attributes a ``game-service`` event to the round it acted FROM.

    The reported round is the 1-based round of PLAY (:func:`round_of_play`), not
    the raw counter, so a round verdict names the round the transcript shows.
    Rounds with no detectable round number do not contribute boundaries.
    """
    ordered = sorted(events, key=lambda e: e.seq)
    if not ordered:
        return []

    boundaries: list[tuple[int, int, int]] = []
    current_round: int | None = None
    round_start_seq = ordered[0].seq
    last_seq = ordered[0].seq

    for event in ordered:
        rn = round_number_of(event)
        if rn is not None:
            if current_round is None:
                # Nothing has been observed yet, so there is no round this event
                # acted FROM; its own state is the best attribution available (a
                # timeline that begins mid-game must report the round it starts in).
                current_round = rn
                round_start_seq = ordered[0].seq
            elif rn != current_round:
                boundaries.append(
                    (round_of_play(current_round), round_start_seq, event.seq)
                )
                current_round = rn
                round_start_seq = event.seq + 1
        last_seq = event.seq
        if is_terminal(event):
            # Terminal status closes the final round at this event -- unless this
            # very event already closed a round above, which would otherwise
            # append an empty span starting after it.
            if round_start_seq <= event.seq:
                close_round = (
                    round_of_play(current_round) if current_round is not None else 1
                )
                boundaries.append((close_round, round_start_seq, event.seq))
            return boundaries

    # No terminal status reached: close the trailing open round at the last seq
    # if a round was ever detected.
    if current_round is not None and (not boundaries or boundaries[-1][2] < last_seq):
        boundaries.append((round_of_play(current_round), round_start_seq, last_seq))
    return boundaries


def assemble_round_input(
    events: list[StoredEvent],
    closing_seq: int,
    *,
    player: str | None = None,
    skip_actions: frozenset[str] = frozenset(),
) -> RoundInput:
    """Assemble a per-round judge input for the round closing at ``closing_seq``.

    When ``player`` is given the round is scored for that player only: just that
    player's moves are included and the already-graded move verdicts for that
    player are attached as roll-up context. ``player=None`` preserves the legacy
    whole-round aggregate behavior.

    Moves whose action is in ``skip_actions`` are left out of the listed moves —
    the same taxonomy that skips them at move scope — and counted so the prompt
    can say how many were omitted.

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
    omitted = 0
    for event in events:
        if event.actor == "agent" and from_seq <= event.seq <= to_seq:
            if player is not None and _move_player(events, event.seq) != player:
                continue
            if non_strategic_reason(event.payload.get("intended_action"), skip_actions):
                omitted += 1
                continue
            moves.append(assemble_move_input(events, event.seq))

    # A round's closing seq is its LAST seq. A round closed by a round-number
    # change closes at the state event that reported it, so the closing state is
    # the board as the round ended; a trailing, still-open round can close at an
    # agent move, which carries no state of its own. Fall back to the nearest
    # recorded state at-or-before it so a round roll-up is never graded with no
    # board at all.
    closing_event = _find_event(events, closing_seq)
    if closing_event is not None and closing_event.actor == "game-service":
        closing_state = closing_event.payload.get("state")
    else:
        nearest = _nearest_state(events, closing_seq, direction="before")
        closing_state = nearest.payload.get("state") if nearest else None
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
        omitted_non_strategic=omitted,
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
    if closing_event is not None and closing_event.actor == "game-service":
        closing_state = closing_event.payload.get("state")
    else:
        # As for a round: the game's last seq is often an agent move, so fall back
        # to the nearest recorded state rather than grading with no final board.
        nearest = _nearest_state(events, closing_seq, direction="before")
        closing_state = nearest.payload.get("state") if nearest else None
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
