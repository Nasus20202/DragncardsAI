from __future__ import annotations

import logging
from typing import Any

from eval_service.judge.assembly import (
    ChildVerdict,
    GameInput,
    MoveInput,
    NeighbourMove,
    RoundInput,
)
from eval_service.judge.state_view import canonical_json, render_state

logger = logging.getLogger(__name__)

# Generous defaults; the evaluator passes the configured caps from Settings.
DEFAULT_MAX_STATE_CHARS = 20_000
DEFAULT_MAX_ROUND_MOVES = 100
DEFAULT_MAX_CONTEXT_REASONING_CHARS = 400

RUBRIC = """\
You are an expert Marvel Champions judge. You grade how well an AI agent played \
a recorded game. You may rely on your knowledge of the Marvel Champions LCG \
rules. Grade ONLY the move(s) and state provided; do not assume hidden \
information.

Score each criterion as an INTEGER from 0 to 10:
- rules_legality: was the move legal and rules-correct given the state?
- strategic_quality: was it a strong strategic choice toward winning?
- tempo_efficiency: did it use the action/economy efficiently (no wasted tempo)?
- threat_resource: did it manage threat and resources well?

Then give an overall_score (0-10 integer), a short rationale paragraph, and a \
list of flags (e.g. "illegal_move", "wasted_resource"); use an empty list when \
there are none.

Respond with ONLY a single JSON object, no prose around it, of the form:
{"scores": {"rules_legality": int, "strategic_quality": int, \
"tempo_efficiency": int, "threat_resource": int}, "overall_score": int, \
"rationale": str, "flags": [str, ...]}
"""


def _json(value: Any) -> str:
    return canonical_json(value)


def _state_json(value: Any, max_chars: int, *, label: str) -> str:
    """Render a per-event state for the prompt: project first, then bound.

    State is by far the largest content in a judge prompt. It is projected down to
    the board the playing agent saw (see :mod:`eval_service.judge.state_view`) and
    ``max_chars`` remains as a backstop for a state shape the projection does not
    recognise, or a projection that is somehow still oversized.
    """
    return render_state(value, max_chars, label=label)


def _system_content(
    prompt_override: str | None,
    skills: list[tuple[str, str]] | None,
) -> str:
    """Assemble the judge system prompt.

    ``prompt_override`` replaces the built-in rubric when provided. Any selected
    skills' markdown is appended as reference material so the judge can rely on
    the supplied rules content.
    """
    base = prompt_override if prompt_override else RUBRIC
    if not skills:
        return base
    blocks = [base, "\n\n# Rules reference skills\n"]
    for name, content in skills:
        blocks.append(f"\n## Skill: {name}\n\n{content}\n")
    return "".join(blocks)


def build_move_messages(
    move: MoveInput,
    *,
    prompt_override: str | None = None,
    skills: list[tuple[str, str]] | None = None,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
    max_context_reasoning_chars: int = DEFAULT_MAX_CONTEXT_REASONING_CHARS,
) -> list[dict[str, str]]:
    """Build a fresh, self-contained judge prompt for a single move."""
    user = (
        f"Evaluate this single agent move (seq {move.target_seq}).\n\n"
        f"Prior game state:\n{_state_json(move.prior_state, max_state_chars, label='prior')}\n\n"
        f"{_neighbour_block(move.context_before, max_context_reasoning_chars, direction='before')}"
        f"Intended action: {_json(move.intended_action)}\n"
        f"Action arguments: {_json(move.arguments)}\n"
        f"Agent's stated reasoning: {_json(move.reasoning)}\n\n"
        f"Resulting game state:\n{_state_json(move.resulting_state, max_state_chars, label='resulting')}\n"
        f"{_neighbour_block(move.context_after, max_context_reasoning_chars, direction='after')}"
    )
    return [
        {"role": "system", "content": _system_content(prompt_override, skills)},
        {"role": "user", "content": user},
    ]


def _neighbour_block(
    neighbours: list[NeighbourMove], max_reasoning_chars: int, *, direction: str
) -> str:
    """Render the neighbouring-move window around the move under judgement.

    The window exists so a move that is one step of a multi-call play is not
    graded as if it stood alone. The following-moves half is labelled as
    completion context rather than an outcome to grade, so the judge does not
    score the decision on hindsight it did not have.
    """
    if not neighbours:
        return ""
    if direction == "before":
        header = (
            f"The agent's {len(neighbours)} immediately PRECEDING move(s) "
            "(context for what this move continues; do not grade them):"
        )
    else:
        header = (
            f"The agent's {len(neighbours)} immediately FOLLOWING move(s) "
            "(context for whether this move completed an intent; do not grade "
            "them and do not judge the decision on hindsight):"
        )
    lines = [header]
    for neighbour in neighbours:
        lines.append(
            f"- seq {neighbour.seq}: action={_json(neighbour.intended_action)} "
            f"args={_json(neighbour.arguments)} "
            f"reasoning={_clip(neighbour.reasoning, max_reasoning_chars)}"
        )
    return "\n".join(lines) + "\n\n"


def _clip(value: Any, max_chars: int) -> str:
    """Serialize a context field, clipped so one verbose neighbour cannot bloat."""
    rendered = _json(value)
    if max_chars > 0 and len(rendered) > max_chars:
        return rendered[:max_chars] + f"...[+{len(rendered) - max_chars} chars]"
    return rendered


def build_round_messages(
    rnd: RoundInput,
    *,
    prompt_override: str | None = None,
    skills: list[tuple[str, str]] | None = None,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
    max_round_moves: int = DEFAULT_MAX_ROUND_MOVES,
) -> list[dict[str, str]]:
    """Build a fresh, self-contained judge prompt for a whole round."""
    moves = rnd.moves
    dropped = 0
    if max_round_moves > 0 and len(moves) > max_round_moves:
        dropped = len(moves) - max_round_moves
        logger.info(
            "Capped round move list from %d to %d moves for judge input "
            "(round %s, seqs %s-%s)",
            len(moves),
            max_round_moves,
            rnd.round_number,
            rnd.from_seq,
            rnd.to_seq,
        )
        moves = moves[:max_round_moves]

    move_blocks = []
    for move in moves:
        move_blocks.append(
            f"- seq {move.target_seq}: action={_json(move.intended_action)} "
            f"args={_json(move.arguments)} reasoning={_json(move.reasoning)}"
        )
    if dropped:
        move_blocks.append(f"- ...[{dropped} further moves omitted]")
    if rnd.omitted_non_strategic:
        move_blocks.append(
            f"- ...[{rnd.omitted_non_strategic} non-strategic action(s) omitted: "
            "searches, session plumbing and pre-game setup carry no play to grade]"
        )
    moves_text = "\n".join(move_blocks) if move_blocks else "(no agent moves)"
    who = f" for {rnd.player}" if rnd.player else ""
    moves_label = (
        f"Moves taken this round{who}" if rnd.player else "Moves taken this round"
    )
    user = (
        f"Evaluate this whole round{who} (round {rnd.round_number}, "
        f"seqs {rnd.from_seq}-{rnd.to_seq}) as a unit.\n\n"
        f"{_child_context_block(rnd.child_verdicts, 'move')}"
        f"{moves_label}:\n{moves_text}\n\n"
        f"Game state at round close:\n{_state_json(rnd.closing_state, max_state_chars, label='closing')}\n"
    )
    return [
        {"role": "system", "content": _system_content(prompt_override, skills)},
        {"role": "user", "content": user},
    ]


def build_game_messages(
    game: GameInput,
    *,
    prompt_override: str | None = None,
    skills: list[tuple[str, str]] | None = None,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
) -> list[dict[str, str]]:
    """Build a fresh, self-contained judge prompt for a whole game, per player.

    The game roll-up is graded holistically given the player's already-graded
    round verdicts as context (not a numeric average of them).
    """
    who = f" for {game.player}" if game.player else ""
    user = (
        f"Evaluate this whole game{who} (seqs {game.from_seq}-{game.to_seq}) as a "
        f"unit, judging how well this player played across the whole game.\n\n"
        f"{_child_context_block(game.child_verdicts, 'round')}"
        f"Final game state:\n{_state_json(game.closing_state, max_state_chars, label='final')}\n"
    )
    return [
        {"role": "system", "content": _system_content(prompt_override, skills)},
        {"role": "user", "content": user},
    ]


def _child_context_block(children: list[ChildVerdict], noun: str) -> str:
    """Render already-graded child verdicts as holistic roll-up context.

    The roll-up judge is given each child's score and rationale so it can grade
    the span holistically (capturing cross-move / cross-round strategy) rather
    than mechanically averaging child scores.
    """
    if not children:
        return ""
    lines = [
        f"Already-graded {noun} verdicts (use as context; grade the span "
        f"holistically, do NOT just average these):"
    ]
    for child in children:
        label = f"{noun} seq {child.target_seq}"
        if child.round_span:
            label += f" (span {child.round_span})"
        lines.append(
            f"- {label}: overall {child.overall_score}/10 — "
            f"{child.rationale or '(no rationale)'}"
        )
    return "\n".join(lines) + "\n\n"
