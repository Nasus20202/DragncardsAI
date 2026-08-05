"""How much skill REFERENCE content one evaluation may carry, and why.

The judge is single-shot: ``BifrostJudgeClient._build_payload`` sends no
``tools`` key and ``parse_verdict`` demands exactly one JSON object, so there is
no loop that could fetch a reference on demand. Everything selected is inlined
into the prompt, always. A prompt over the model's context window is therefore
not a slow prompt, it is a provider error -- arriving per target, inside the
worker, after the batch is already running.

So a bound stays. What this module does is make the bound EQUAL THE PHYSICS
rather than be an opinion about how many rules files a judge ought to need: the
context window, in characters, less everything else the prompt may hold at the
caps the operator already configured. What is left is the reference budget.

**The reserve is the WORST of the three scopes, not their sum.** One judge
configuration serves move, round and game prompts, and they hold different
things: a move prompt has a neighbour block and two states but no roll-up
context; a round prompt has a move list, one state and its moves' verdicts; a
game prompt has one state and its rounds' verdicts. Summing them would reserve
for a prompt that cannot exist and refuse selections that fit every real one.

Every reserve term is an existing setting read back, which is what makes the
number defensible and gives an operator a real lever in each direction. Three
constants are not, and they are projections rather than ceilings:

* ``MOVE_BLOCK_OVERHEAD_CHARS`` -- a move line is
  ``- seq N: action=<json> args=<json> reasoning=<clipped>``. The reasoning is
  clipped by a setting; ``args`` is clipped by nothing, because a move's
  arguments are what legality is judged on and truncating them would change
  verdicts. So this covers the line text, the action name and a projected
  arguments object.
* ``CHILD_BLOCK_OVERHEAD_CHARS`` -- the label, span and score of one roll-up
  child verdict, whose rationale IS clipped.
* ``PROMPT_FRAME_CHARS`` -- the rubric measures 1,526 chars and the
  orchestrated-mode note 468; the rest covers section labels, the round's
  illegal-action findings, and the graded move's OWN action/arguments/reasoning
  block, which is deliberately never clipped.

All three are deliberately generous. They over-reserve, so the budget is
conservative: it may refuse a selection that would have fitted, and must not
admit one that would not.

Token figures are PROJECTIONS at ~4 characters per token -- the convention DRA-41
established. No judge call has ever been made against this code path on this
stack (``EVAL_JUDGE_OPENROUTER_API_KEY`` is unset), so nothing here is a measured
token count.
"""

from __future__ import annotations

from dataclasses import dataclass

from eval_service.config import Settings

__all__ = [
    "CHARS_PER_TOKEN",
    "CHILD_BLOCK_OVERHEAD_CHARS",
    "MOVE_BLOCK_OVERHEAD_CHARS",
    "PROMPT_FRAME_CHARS",
    "UNCLIPPED_TEXT_PROJECTION_CHARS",
    "ReferenceBudget",
    "reference_budget",
]

# Projection, not a tokenizer. See the module docstring.
CHARS_PER_TOKEN = 4
# Per move line, everything but the clipped reasoning field.
MOVE_BLOCK_OVERHEAD_CHARS = 400
# Per roll-up child verdict, everything but the clipped rationale.
CHILD_BLOCK_OVERHEAD_CHARS = 200
# Rubric + mode note + labels + illegal-action findings + the graded move itself.
PROMPT_FRAME_CHARS = 12_000
# A per-item clip of ``0`` means "do not clip" in ``prompt._clip``. Reserving 0
# for it would make switching a clip OFF *raise* the budget while the text it
# stopped bounding becomes unbounded -- the reserve would move the wrong way. So
# an unclipped field is reserved at this projection instead.
UNCLIPPED_TEXT_PROJECTION_CHARS = 2_000


def _clip_reserve(configured: int) -> int:
    """Chars to reserve for a field clipped at ``configured`` (``0`` = uncapped)."""
    return configured if configured > 0 else UNCLIPPED_TEXT_PROJECTION_CHARS


@dataclass(frozen=True)
class ReferenceBudget:
    """The derived reference budget, carrying every term that produced it.

    The terms are kept rather than folded away so a refusal can show its own
    arithmetic: a user who cannot see reference sizes in the dashboard learns
    what to drop only from this message.
    """

    window_tokens: int
    window_chars: int
    completion_chars: int
    #: Which scope's prompt is the largest, and therefore what was reserved.
    binding_scope: str
    state_chars: int
    move_context_chars: int
    child_context_chars: int
    frame_chars: int
    prompt_override_chars: int
    skill_chars: int
    skill_count: int
    #: Effective budget after the optional operator cap. ``chars`` is what a
    #: selection is measured against.
    chars: int
    #: The window-derived budget before the operator cap, so a refusal can say
    #: whether the cap or the window is what bit.
    derived_chars: int
    operator_cap_chars: int

    @property
    def capped_by_operator(self) -> bool:
        return 0 < self.operator_cap_chars < self.derived_chars

    def exceeded_by(self, total_chars: int) -> bool:
        return total_chars > self.chars

    def refusal(self, total_chars: int) -> str:
        """The 400 body for a selection of ``total_chars``.

        Verbose on purpose. It is shown once, at the moment the user is blocked,
        and it is the only place the arithmetic is visible -- the skills
        catalogue reports reference NAMES only, so the dashboard cannot warn
        before the request is made. The reserve breakdown is present whether or
        not an operator cap is what bit, because it is what tells the user which
        setting to change.
        """
        reserve = (
            f"A {self.window_tokens}-token context window is ~{self.window_chars} "
            f"chars at ~{CHARS_PER_TOKEN} chars/token; reserving "
            f"{self.completion_chars} for the completion, {self.state_chars} for "
            f"game state, {self.move_context_chars} for round context, "
            f"{self.child_context_chars} for roll-up context, {self.frame_chars} "
            f"for the prompt frame (worst case is the {self.binding_scope} "
            f"prompt), {self.prompt_override_chars} for the prompt override and "
            f"{self.skill_chars} for {self.skill_count} selected SKILL.md file(s) "
            f"leaves {self.derived_chars}."
        )
        cap = (
            " EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS then lowers that to "
            f"{self.operator_cap_chars}."
            if self.capped_by_operator
            else ""
        )
        return (
            f"selected skill references total at least {total_chars} characters, "
            f"over the {self.chars} character budget by "
            f"{total_chars - self.chars}; references are never truncated. "
            f"{reserve}{cap} Deselect references or skills, lower "
            "EVAL_JUDGE_MOVE_CONTEXT_BEFORE / EVAL_JUDGE_MOVE_CONTEXT_AFTER or "
            "EVAL_JUDGE_MAX_STATE_CHARS, or set "
            "EVAL_JUDGE_CONTEXT_WINDOW_TOKENS to your judge model's real "
            "context window."
        )


def reference_budget(
    settings: Settings,
    *,
    skill_chars: int = 0,
    skill_count: int = 0,
    prompt_override_chars: int = 0,
) -> ReferenceBudget:
    """Derive the reference budget for one evaluation's judge configuration.

    ``skill_chars`` is the combined size of the ``SKILL.md`` files this request
    selects, charged because they share the same prompt. ``prompt_override_chars``
    is added ON TOP of the frame rather than swapped for the rubric it replaces;
    that double-counts the rubric's 1,526 chars, always in the conservative
    direction, and keeps the arithmetic in the refusal message followable.
    """
    window_chars = settings.eval_judge_context_window_tokens * CHARS_PER_TOKEN
    completion_chars = settings.eval_judge_max_tokens * CHARS_PER_TOKEN
    state = settings.eval_judge_max_state_chars

    move_line = (
        _clip_reserve(settings.eval_judge_move_context_reasoning_chars)
        + MOVE_BLOCK_OVERHEAD_CHARS
    )
    child_line = (
        _clip_reserve(settings.eval_judge_max_child_rationale_chars)
        + CHILD_BLOCK_OVERHEAD_CHARS
    )
    round_moves = settings.eval_judge_max_round_moves
    neighbours = (
        settings.eval_judge_move_context_before + settings.eval_judge_move_context_after
    )

    # (state, move-context, roll-up-context) per scope. See the module docstring
    # for why this is a max and not a sum.
    scopes = {
        # Prior + resulting state, and the graded move's neighbours either side.
        "move": (2 * state, neighbours * move_line, 0),
        # Closing state, the round's move list, and its moves' verdicts.
        "round": (state, round_moves * move_line, round_moves * child_line),
        # Final state and the game's round verdicts.
        "game": (state, 0, round_moves * child_line),
    }
    binding_scope, (state_chars, move_context_chars, child_context_chars) = max(
        scopes.items(), key=lambda item: sum(item[1])
    )

    derived = max(
        0,
        window_chars
        - completion_chars
        - state_chars
        - move_context_chars
        - child_context_chars
        - PROMPT_FRAME_CHARS
        - prompt_override_chars
        - skill_chars,
    )
    cap = settings.eval_judge_max_skill_reference_chars
    # The cap only ever LOWERS. Setting it above the window bought nothing but a
    # provider error later, so it is no longer a way to raise the budget.
    effective = min(derived, cap) if cap > 0 else derived

    return ReferenceBudget(
        window_tokens=settings.eval_judge_context_window_tokens,
        window_chars=window_chars,
        completion_chars=completion_chars,
        binding_scope=binding_scope,
        state_chars=state_chars,
        move_context_chars=move_context_chars,
        child_context_chars=child_context_chars,
        frame_chars=PROMPT_FRAME_CHARS,
        prompt_override_chars=prompt_override_chars,
        skill_chars=skill_chars,
        skill_count=skill_count,
        chars=effective,
        derived_chars=derived,
        operator_cap_chars=cap,
    )
