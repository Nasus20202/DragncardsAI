from __future__ import annotations

import logging
from typing import Any

from eval_service.judge.assembly import (
    ChildVerdict,
    GameInput,
    IllegalActionFinding,
    MoveInput,
    NeighbourMove,
    RoundInput,
)
from eval_service.judge.events import SESSION_MODE_ORCHESTRATED
from eval_service.judge.rounds import round_label
from eval_service.judge.skill_resources import LoadedReference
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

A single game decision is normally executed as SEVERAL recorded actions: playing \
an ally and using its ability is ONE play made of moving the card into play, \
exhausting a character to pay the cost, and assigning the damage. When you grade \
one action, grade it as the STEP IT IS within the play its round reveals. A \
legal, necessary step of a sound play is a good move even when it accomplishes \
nothing on its own, so do NOT score it down for being incomplete — and do NOT \
charge the same play against every action that makes it up.

Then give an overall_score (0-10 integer), a short rationale paragraph, and a \
list of flags (e.g. "illegal_move", "wasted_resource"); use an empty list when \
there are none.

Respond with ONLY a single JSON object, no prose around it, of the form:
{"scores": {"rules_legality": int, "strategic_quality": int, \
"tempo_efficiency": int, "threat_resource": int}, "overall_score": int, \
"rationale": str, "flags": [str, ...]}
"""


ORCHESTRATED_MODE_NOTE = """\
This play was recorded in ORCHESTRATED mode: each player seat was played by a \
SEPARATE agent, holding its own conversation context and its own persona. No seat \
could see another seat's reasoning or private deliberation — only the shared board \
and whatever the coordinating agent chose to pass along. Do NOT penalise a seat \
for failing to account for information it could not have seen, and do not read \
imperfect coordination between seats as a mistake by either one.

"""


def _mode_note(session_mode: str) -> str:
    """The orchestration-mode framing for a projection, empty in chat mode.

    Empty rather than "this was chat mode" on purpose: a chat projection has to
    read EXACTLY as it read before orchestrated mode existed, byte for byte, or
    verdicts recorded before this change stop being comparable with verdicts
    recorded after it. Every mode-dependent addition in this module is gated the
    same way, and ``tests/unit/test_judge_session_mode.py`` pins the chat prompts
    against literal expected strings so the guarantee cannot quietly lapse.
    """
    if session_mode != SESSION_MODE_ORCHESTRATED:
        return ""
    return ORCHESTRATED_MODE_NOTE


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
    skill_references: list[LoadedReference] | None = None,
) -> str:
    """Assemble the judge system prompt.

    ``prompt_override`` replaces the built-in rubric when provided. Any selected
    skills' markdown is appended as reference material so the judge can rely on
    the supplied rules content, and any selected REFERENCE files are appended
    beneath the skill they belong to — a skill's references are part of its
    content, and a judge given only ``SKILL.md`` grades against a fraction of the
    rulebook it was pointed at.

    With no references selected this emits the exact bytes it emitted before
    references existed: the reference loop contributes nothing, so every judge
    config that predates this argument produces a byte-identical prompt and its
    verdicts stay comparable.
    ``test_judge_skill_references.py::test_a_reference_free_system_prompt_matches_the_pre_change_literal``
    pins that against a LITERAL. Note that ``test_judge_session_mode.py`` does NOT
    help here -- it asserts the USER message, and nothing but that literal covers
    a byte of this one.
    """
    base = prompt_override if prompt_override else RUBRIC
    if not skills and not skill_references:
        return base
    by_skill = _references_by_skill(skill_references)
    blocks = [base, "\n\n# Rules reference skills\n"]
    for name, content in skills or []:
        blocks.append(f"\n## Skill: {name}\n\n{content}\n")
        blocks.extend(_reference_blocks(by_skill.pop(name, [])))
    # A reference whose SKILL.md was NOT selected still belongs to a skill, and
    # the heading says so rather than implying the judge holds the whole thing.
    for name, references in by_skill.items():
        blocks.append(f"\n## Skill: {name} (references only)\n")
        blocks.extend(_reference_blocks(references))
    return "".join(blocks)


def _references_by_skill(
    references: list[LoadedReference] | None,
) -> dict[str, list[LoadedReference]]:
    """Group references under their skill, preserving the selected order."""
    grouped: dict[str, list[LoadedReference]] = {}
    for reference in references or []:
        grouped.setdefault(reference.skill, []).append(reference)
    return grouped


def _reference_blocks(references: list[LoadedReference]) -> list[str]:
    return [
        f"\n### Reference: {reference.reference}\n\n{reference.content}\n"
        for reference in references
    ]


def build_move_messages(
    move: MoveInput,
    *,
    prompt_override: str | None = None,
    skills: list[tuple[str, str]] | None = None,
    skill_references: list[LoadedReference] | None = None,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
    max_context_reasoning_chars: int = DEFAULT_MAX_CONTEXT_REASONING_CHARS,
) -> list[dict[str, str]]:
    """Build a fresh, self-contained judge prompt for a single move."""
    user = (
        f"{_mode_note(move.session_mode)}"
        f"Evaluate this single agent move (seq {move.target_seq}){_round_scope(move)}.\n"
        "The move is one action of that round's play; grade it as its step of "
        "that play, not as a play in its own right.\n\n"
        f"Prior game state:\n{_state_json(move.prior_state, max_state_chars, label='prior')}\n\n"
        f"{_neighbour_block(move.context_before, max_context_reasoning_chars, direction='before')}"
        f"Intended action: {_json(move.intended_action)}\n"
        f"Action arguments: {_json(move.arguments)}\n"
        f"Agent's stated reasoning: {_json(move.reasoning)}\n\n"
        f"Resulting game state:\n{_state_json(move.resulting_state, max_state_chars, label='resulting')}\n"
        f"{_neighbour_block(move.context_after, max_context_reasoning_chars, direction='after')}"
    )
    return [
        {
            "role": "system",
            "content": _system_content(prompt_override, skills, skill_references),
        },
        {"role": "user", "content": user},
    ]


def _round_scope(move: MoveInput) -> str:
    """The round clause for a move prompt, empty when no round contains the move.

    Reads as ``in Round 3 (seqs 41-72)``. The label is the round OF PLAY, never
    the raw recorded number: DragnCards counts COMPLETED rounds, so showing a
    judge "round 0" would misstate the game position.
    """
    if move.round_number is None or move.round_span is None:
        return ""
    label = round_label(move.round_number)
    return f" in {label} (seqs {move.round_span[0]}-{move.round_span[1]})"


def _neighbour_block(
    neighbours: list[NeighbourMove], max_reasoning_chars: int, *, direction: str
) -> str:
    """Render the round's other moves around the move under judgement.

    The context is the graded move's own ROUND, so a move that is one step of a
    multi-call play is never graded as if it stood alone. The later-in-round half
    is labelled as completion context rather than an outcome to grade, so the
    judge does not score the decision on hindsight it did not have.
    """
    if not neighbours:
        return ""
    if direction == "before":
        header = (
            f"The agent's {len(neighbours)} move(s) EARLIER IN THIS ROUND, "
            "oldest first (context for the play this move continues; do not "
            "grade them):"
        )
    else:
        header = (
            f"The agent's {len(neighbours)} move(s) LATER IN THIS ROUND, oldest "
            "first (context for whether this move completed the play it belongs "
            "to; do not grade them and do not judge the decision on hindsight):"
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
    skill_references: list[LoadedReference] | None = None,
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
        f"{_mode_note(rnd.session_mode)}"
        f"Evaluate this whole round{who} ({round_label(rnd.round_number)}, "
        f"seqs {rnd.from_seq}-{rnd.to_seq}) as a unit.\n\n"
        f"{_child_context_block(rnd.child_verdicts, 'move')}"
        f"{_illegal_action_block(rnd.illegal_actions, rnd.player)}"
        f"{moves_label}:\n{moves_text}\n\n"
        f"Game state at round close:\n{_state_json(rnd.closing_state, max_state_chars, label='closing')}\n"
    )
    return [
        {
            "role": "system",
            "content": _system_content(prompt_override, skills, skill_references),
        },
        {"role": "user", "content": user},
    ]


def build_game_messages(
    game: GameInput,
    *,
    prompt_override: str | None = None,
    skills: list[tuple[str, str]] | None = None,
    skill_references: list[LoadedReference] | None = None,
    max_state_chars: int = DEFAULT_MAX_STATE_CHARS,
) -> list[dict[str, str]]:
    """Build a fresh, self-contained judge prompt for a whole game, per player.

    The game roll-up is graded holistically given the player's already-graded
    round verdicts as context (not a numeric average of them).
    """
    who = f" for {game.player}" if game.player else ""
    user = (
        f"{_mode_note(game.session_mode)}"
        f"Evaluate this whole game{who} (seqs {game.from_seq}-{game.to_seq}) as a "
        f"unit, judging how well this player played across the whole game.\n\n"
        f"{_child_context_block(game.child_verdicts, 'round')}"
        f"Final game state:\n{_state_json(game.closing_state, max_state_chars, label='final')}\n"
    )
    return [
        {
            "role": "system",
            "content": _system_content(prompt_override, skills, skill_references),
        },
        {"role": "user", "content": user},
    ]


def _illegal_action_block(
    findings: list[IllegalActionFinding], player: str | None
) -> str:
    """Render the round's recorded illegal-action findings as evidence.

    Two things this block has to get right.

    **It is evidence, not a verdict**, and the text says so. The orchestrator
    decided legality from game state, which is a stronger source than anything the
    judge can reconstruct from a move list — but a recorded violation is one input
    to a round's score, not the score. Presenting it as a finding to weigh keeps a
    round with one corrected slip from collapsing to a zero, and equally keeps the
    judge from having to guess at a violation the orchestrator already established.

    **A resolved finding reads differently from an open one.** Resolved findings
    stay on the timeline because "the seat undid it" is itself part of the record,
    so each entry states which it is, and a resolution note is shown when one was
    recorded.
    """
    if not findings:
        return ""
    lines = [
        "Illegal-action findings the orchestrator recorded for this round. This is "
        "EVIDENCE, not a verdict: legality was decided from the recorded game "
        "state, and you weigh a finding alongside everything else here rather "
        "than letting it settle the score by itself."
    ]
    for finding in findings:
        seat = finding.player or "an unnamed seat"
        if finding.is_resolved:
            state = "RESOLVED"
            if finding.resolution_note:
                state += f" — {finding.resolution_note}"
        else:
            state = "OPEN, not undone"
        lines.append(f"- seq {finding.seq}, {seat}: {finding.violation} [{state}]")
    if player:
        lines.append(
            f"A finding naming a seat other than {player} explains the position "
            f"this round produced; it is not {player}'s play to answer for."
        )
    return "\n".join(lines) + "\n\n"


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
