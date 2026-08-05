# Tasks

## 1. Reference resolution in eval-service

- [x] 1.1 Add `services/eval-service/src/eval_service/judge/skill_resources.py`
      with `SkillReferenceError`, `parse_reference_selection` and
      `load_reference_content`, confining a caller-supplied path to its own skill
      directory (absolute path, `..`, non-canonical form, symlink, non-`.md`,
      directory and `SKILL.md` all refused) behind one refusal message.
- [x] 1.2 Extend `SkillResolver` with `load_references(selections)` returning
      `(skill, reference, content)` triples, reusing the per-name content cache
      pattern already in the class.
- [x] 1.3 Add `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` (default 60,000) to
      `Settings` and enforce it as a total budget across the selection, raising a
      dedicated error naming the measured total and the limit.

## 2. Judge config and request surface

- [x] 2.1 Add `skill_references: list[str] | None` to `JudgeConfig` with
      `MAX_SKILL_REFERENCES = 8`.
- [x] 2.2 Add `skill_references: tuple[str, ...] = ()` to `ResolvedJudgeConfig`;
      `to_json()` omits the key when empty so existing digests are unchanged, and
      `from_json()` reads it back.
- [x] 2.3 Resolve and validate references in `resolve_judge_config` (unknown
      skill, unresolvable reference, over-budget) so a bad selection is a 400
      before any target is enqueued.
- [x] 2.4 Sort `skill_references` in `judge_config_digest` alongside `skills`, so
      a reordered selection hashes identically.
- [x] 2.5 Map the new errors to 400 in `RequestService.create`.

## 3. Prompt assembly

- [x] 3.1 Add a `skill_references` argument to `_system_content`,
      `build_move_messages`, `build_round_messages` and `build_game_messages`,
      rendering each reference under its skill and giving a references-only skill
      its own block.
- [x] 3.2 Resolve and pass references from `Evaluator._produce_verdict` at all
      three scopes.

## 4. Discovery

- [x] 4.1 Add `references: list[str]` to the agent-orchestrator's
      `SkillDefinitionResponse` and populate it from
      `SkillRegistry.list_reference_files` in `GET /skills`.
- [x] 4.2 Add `references` to the dashboard's `SkillDefinitionResponse` type.
- [x] 4.3 Add `selectedSkillReferences` to `JudgeDraft`, assemble it into
      `judge.skill_references`, and drop selections whose skill is deselected.
- [x] 4.4 Render the selected skills' reference files as individually selectable
      entries in the judge panel.

## 5. Tests

- [x] 5.1 Path-safety tests in eval-service: absolute path, `..` out, `..` back
      in, symlink to outside the skill, symlinked directory component, in-skill
      symlink, non-`.md`, directory, `SKILL.md` itself, unknown skill, malformed
      selection, and a refusal that does not disclose whether its target exists.
- [x] 5.2 A test that fails without the fix: a reference selection reaches the
      judge system prompt.
- [x] 5.3 Byte-identity test: the system prompt with no reference selections is
      identical to the prompt built before this change, for rubric and
      prompt-override paths.
- [x] 5.4 Digest test: `to_json()` of a reference-free config is unchanged and
      hashes to the pinned pre-change digest; a reference selection changes it;
      reordering a selection does not.
- [x] 5.5 Budget test: an over-budget selection is refused with the measured
      total, and nothing is truncated.
- [x] 5.6 Prompt test: references reach the built messages at move, round and
      game scope.
- [x] 5.7 Integration test: a reference selection survives request -> persisted
      target -> worker -> the judge client's messages; a selection outside the
      skill is a `RequestError` that enqueues nothing and spends no judge call.
- [x] 5.8 Orchestrator test: `GET /skills` reports a skill's reference files and
      an empty list for a skill with none.
- [x] 5.9 Dashboard tests: reference toggles appear for a selected skill, feed
      `judge.skill_references`, and are dropped when the skill is deselected.

## 6. Documentation and configuration

- [x] 6.1 Add `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` (and the previously
      undocumented `SKILL_ROOTS`) to the configuration table in
      `services/eval-service/README.md`. No `.env.example` or `docker-compose`
      entry: eval-service has no `.env.example`, and compose declares none of the
      sibling judge caps either — the service's `SKILL_ROOTS` comes from its
      Dockerfile and the new budget uses its default.
- [x] 6.2 Document the reference selection in a new "Rules skills and their
      references" section of the eval-service README — the selection format, that
      a reference may be selected without its `SKILL.md`, why the skill is inlined
      rather than fetched with a tool, the two bounds, that references are never
      truncated, the path rules, and why `EVALUATOR_VERSION` is not bumped. Add
      `judge` to the `POST /evaluations` body documentation.
- [x] 6.3 Document `references` on `GET /skills` in
      `services/agent-orchestrator/README.md`.
- [x] 6.4 Add a core-concept section to `services/eval-service/AGENTS.md`: the
      judge is single-shot with no tool loop, and the three invariants that
      hold the reference design together (byte-identity + digest omission, no
      truncation, one refusal message for every path rule).

## 7. Verification

- [x] 7.1 `./scripts/lint.sh --fix`
- [x] 7.2 `./scripts/test.sh unit`
- [x] 7.3 `./scripts/test.sh integration eval-service`
- [x] 7.4 `openspec validate --all`

## 8. Review findings addressed

Raised by `/security-review` and `/code-review` after the implementation landed.

- [x] 8.1 Reject a NEGATIVE `EVAL_JUDGE_MAX_SKILL_REFERENCE_CHARS` with a
      validator: the budget check is `> 0`, so a negative value disabled the
      budget entirely while reading like a tight one.
- [x] 8.2 Store the CANONICAL selection rather than the caller's string, so
      whitespace variants of one selection cannot produce two idempotency keys
      and a duplicate verdict.
- [x] 8.3 Deduplicate selections, so one file named twice is neither inlined
      twice nor charged to the budget twice.
- [x] 8.4 Delete `SkillResolver._reference_cache`: it never invalidated, so it
      pinned the largest and most frequently edited files in the corpus to their
      boot-time contents, and the read it saved is invisible next to the LLM call
      it precedes.
- [x] 8.5 Log the specific refusal reason server-side while keeping the single
      client-facing message.
- [x] 8.6 Replace the tautological byte-identity test with a LITERAL assertion of
      the system prompt (verified to fail on a one-character change to the
      heading), and correct the `prompt.py` docstring and `design.md`, which both
      claimed a guarantee that `test_judge_session_mode.py` does not cover — it
      asserts the USER message.
- [x] 8.7 Correct `design.md` §2a: the digest identifies the *selection*, not the
      *content*, so the argument against a tool loop is comparative, not
      categorical.
- [x] 8.8 Simplify `_REJECTED_PARTS` to a `".."` check — `pathlib` normalises
      `""` and `"."` away, so two thirds of the set was dead.
- [x] 8.9 Flatten FastAPI's validation `detail` array in the dashboard's
      `readJson`, which surfaced every schema-limit rejection as
      `[object Object]`, and cap reference selection at 8 in the UI with a
      counter so the 422 is unreachable.
- [x] 8.10 Back-port the null-byte `ValueError` fix to the agent-orchestrator's
      `load_reference_content`, where it escaped the tool handler and failed the
      whole job.
- [x] 8.11 Omit symlinks from the orchestrator's `list_reference_files`, so the
      catalogue never advertises a reference its own loader refuses.
- [x] 8.12 Take the catalogue's references from the definition's PATH, not its
      name, so `GET /skills` stops re-scanning every skill root once per skill.
- [x] 8.13 Cover what was untested: the skill-resolution failure handler, a
      duplicated selection, a prompt mixing an inlined skill with a
      references-only skill, canonical-form storage, the negative budget, the
      orchestrator null-byte and symlink-listing fixes, and the `readJson`
      detail shapes.

