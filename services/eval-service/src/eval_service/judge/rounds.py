from __future__ import annotations

from eval_service.schemas.history import StoredEvent


def round_label(round_of_play: int | None) -> str:
    """A human/judge-facing label for a round of play ("Round 1").

    Takes the round OF PLAY, not DragnCards' raw ``roundNumber`` — that counter
    counts COMPLETED rounds and reads 0 throughout the first round of play, so
    labelling it directly would name every round one too low. The conversion lives
    in :func:`eval_service.judge.assembly.round_of_play`, and
    ``detect_round_boundaries`` has already applied it to the numbers this module
    is given.
    """
    return "Unknown round" if round_of_play is None else f"Round {round_of_play}"


def round_span_containing(
    boundaries: list[tuple[int, int, int]], target_seq: int
) -> tuple[int, int, int] | None:
    """The ``(round_of_play, from_seq, to_seq)`` boundary containing ``target_seq``.

    Takes already-detected boundaries rather than detecting them, so this module
    has no dependency on the round-boundary detection it consumes (and no import
    cycle with it). Returns None when no detected round contains the sequence —
    which happens legitimately before any recorded state carries a round number.
    """
    for boundary in boundaries:
        if boundary[1] <= target_seq <= boundary[2]:
            return boundary
    return None


def neighbour_events(
    events: list[StoredEvent],
    target_seq: int,
    *,
    direction: str,
    limit: int,
    span: tuple[int, int] | None = None,
) -> list[StoredEvent]:
    """The agent moves neighbouring ``target_seq`` on one side, in seq order.

    ``span`` is the ROUND the graded move belongs to. When it is given the
    selection is confined to that round: a move is judged as a step of the play
    its round reveals, so context from an adjacent round is a different turn on a
    different board and context that stops inside the round hides the rest of the
    play. When ``span`` is None (no round could be detected for the move) the
    selection falls back to the nearest moves across the whole timeline, so a
    move never loses its context because boundary detection produced nothing.

    ``limit`` is a SAFETY BACKSTOP against a pathological round, not the
    mechanism that decides the window: it keeps the ``limit`` moves NEAREST the
    graded one and is set high enough to cover a whole round by default. A limit
    of 0 selects nothing, which is how the following side is configured away
    entirely.

    Non-strategic actions are deliberately NOT filtered out. They are skipped as
    evaluation TARGETS (a card search cannot be a wrong decision), but as context
    they carry the agent's intent — "searched for Med Team, then played Med Team"
    is more legible than "played Med Team" alone.
    """
    if limit <= 0:
        return []
    candidates = [
        event
        for event in events
        if event.actor == "agent"
        and (
            event.seq < target_seq if direction == "before" else event.seq > target_seq
        )
        and (span is None or span[0] <= event.seq <= span[1])
    ]
    candidates.sort(key=lambda e: e.seq)
    return candidates[-limit:] if direction == "before" else candidates[:limit]
