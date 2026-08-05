# Tasks

## 1. eval-service: derive the budget from the context window

- [x] 1.1 Add `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` to `Settings` (default `128_000`,
      mirroring the orchestrator's `CONTEXT_WINDOW_SIZE`), with a validator
      refusing values below 1.
- [x] 1.2 Change `eval_judge_max_skill_reference_chars` to default `0` and
      document its new meaning: `0` = no cap beyond the window, `> 0` = an
      additional cap that only ever lowers the derived budget, `< 0` still
      refused.
- [x] 1.3 Add `services/eval-service/src/eval_service/judge/reference_budget.py`
      with `CHARS_PER_TOKEN`, `PROMPT_FRAME_CHARS`, `NEIGHBOUR_OVERHEAD_CHARS`, a
      `ReferenceBudget` dataclass carrying every reserve term, and
      `reference_budget(settings, *, skill_chars, prompt_override_chars)`.
- [x] 1.4 Give `ReferenceBudget` the refusal message: measured total, budget,
      overage, each reserve term, and the settings that raise the budget.
- [x] 1.5 `SkillResolver.load_references` takes a `ReferenceBudget` instead of a
      raw `max_total_chars`, and raises `SkillReferenceBudgetError` built from it.
- [x] 1.6 `resolve_judge_config` keeps the loaded `SKILL.md` content it already
      reads, charges its size to the reserve, and passes the prompt override's
      length too.

## 1b. eval-service: make the reserve a real ceiling

- [x] 1b.1 `build_round_messages` clips each move's `reasoning` at
      `EVAL_JUDGE_MOVE_CONTEXT_REASONING_CHARS`, as `_neighbour_block` already
      does for the same field.
- [x] 1b.2 `_child_context_block` bounds roll-up child verdicts by COUNT
      (`EVAL_JUDGE_MAX_ROUND_MOVES`, with an omission line and a log) and each
      rationale by a new `EVAL_JUDGE_MAX_CHILD_RATIONALE_CHARS` (600).
- [x] 1b.3 The reserve is the WORST of the move/round/game scopes, not their sum.
- [x] 1b.4 A per-item clip of `0` ("do not clip") reserves
      `UNCLIPPED_TEXT_PROJECTION_CHARS` so switching a clip off cannot RAISE the
      budget.

## 2. eval-service: the count ceiling stops being a policy

- [x] 2.1 Raise `MAX_SKILL_REFERENCES` from `8` to `1_000` and rewrite its comment
      to say it is a request-body sanity ceiling, not a selection bound.
- [x] 2.2 Add a per-ENTRY `MAX_SKILL_REFERENCE_LENGTH` (512), since the list
      ceiling is now 1,000 rather than 8.

## 3. eval-service tests

- [x] 3.1 A selection of all 21 `marvel-champions-rules-reference` files plus its
      `SKILL.md` is ACCEPTED at the default settings (fails before the change on
      both bounds).
- [x] 3.2 More than 8 references is accepted (fails before the change: schema 422).
- [x] 3.3 A selection that exceeds the derived budget is refused, and the message
      names the total, the budget, the overage, the window and the reserve terms.
- [x] 3.4 Raising `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` turns that refusal into an
      acceptance; lowering it turns an acceptance into a refusal.
- [x] 3.5 A positive `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` lowers the budget; a
      value above the derived budget does NOT raise it.
- [x] 3.6 Selected `SKILL.md` bytes and a prompt override are charged to the
      reserve, so the same reference selection can pass without them and fail with
      them.
- [x] 3.7 `reference_budget` arithmetic is pinned term by term at the defaults.
- [x] 3.8 A reference-free judge config still produces an unchanged
      `judge_config_digest` and a byte-identical system prompt (regression).
- [x] 3.9 The reserve is the worst scope, not the sum; a clip switched off lowers
      the budget; `min(derived, cap)` with `derived == 0`; a cap composed with
      selected skills.
- [x] 3.10 A round prompt clips a verbose move reasoning, and a roll-up bounds
      child verdicts by count and rationale length.

## 4. dashboard: select all

- [x] 4.1 Delete `MAX_SKILL_REFERENCES` and the `atLimit` row-disabling from
      `judge-skill-references.tsx`; the counter becomes `selected / total`.
- [x] 4.2 Add header "Select all" / "Clear all" over every reference of every
      selected skill.
- [x] 4.3 Add per-skill-group "All" / "None".
- [x] 4.4 Keep selection order stable and free of duplicates when select-all runs
      over an already-partial selection.

## 5. dashboard tests

- [x] 5.1 A ninth reference is selectable and no row is ever disabled by count
      (fails before the change).
- [x] 5.2 Select all selects every reference of every selected skill; clear all
      empties the selection.
- [x] 5.3 A group's All / None touches only that group's references.
- [x] 5.4 Select all over a partial selection produces no duplicates.
- [x] 5.5 The `http-error-detail` test that names the count limit is updated to the
      budget refusal.

## 6. Docs

- [x] 6.1 `services/eval-service/README.md`: the new setting, the changed meaning
      and default of `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS`, the derivation, and
      the new count ceiling.
- [x] 6.2 `services/eval-service/AGENTS.md`: same, where it describes reference
      handling, plus the rule that a new repeated prompt element needs a cap AND
      a reserve term.
- [x] 6.3 `services/eval-service/.env.example` and `docker-compose.yaml` expose
      `EVAL_JUDGE_CONTEXT_WINDOW_TOKENS` and the changed
      `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS`.
- [x] 6.4 `services/dashboard/features/shared/lib/types.ts` no longer documents a
      limit of 8 on `skill_references`.

## 7. Verification

- [x] 7.1 `./scripts/lint.sh --fix`
- [x] 7.2 `pnpm typecheck` in `services/dashboard`
- [x] 7.3 `./scripts/test.sh unit`
- [x] 7.4 `./scripts/test.sh integration`
- [x] 7.5 `openspec validate --all` (one pre-existing failure: `spec/typed-game-actions`)
- [x] 7.6 Drive the Evaluate panel's select-all in a browser on a free high port.
