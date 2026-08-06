# Give every shipped skill a strict loop and evidence-backed guardrails

## Why

`skills/` is a runtime root. Its contents are copied into the agent-orchestrator
and eval-service images and reach the model three ways — names and descriptions in
the system prompt, `SKILL.md` bodies through `load_skill` or `@mention` inlining,
and reference files through `load_skill_reference` or a judge's explicit
selection. Editing it changes what the bot is told, so it is a production change.

Two of the five skills have not been touched since the corpus was first written
(`dragncards` and `marvel-champions-learn-to-play`, both 2026-05-07;
`marvel-champions-rules-reference` 2026-05-13), while `marvel-champions-play` and
`marvel-champions-orchestrator` were rewritten in the last two weeks. The gap
shows in three concrete ways.

**The procedures do not say when to stop or what to do on failure.** DRA-57 asks
for "a valid, clear, and strict loop". `marvel-champions-play/SKILL.md` has a
seven-step turn loop with no entry conditions, no per-step verification gate, and
no failure ladder — the recovery material exists but lives in
`resources/recovery.md`, which the agent only reads *after* something has already
gone wrong. `marvel-champions-learn-to-play` has no procedure at all: it is a
709-line rules dump with no `references/`, so every agent that loads it pays
32,301 characters to get five paragraphs of round flow.

**The skills do not mention the guardrails that already exist in the runtime.**
Three orchestrated-mode tools ship today and appear in **no** skill file:
`report_illegal_action`, `resolve_illegal_action` (orchestrator only) and
`list_my_illegal_actions` (seat only). The seat guard
(`runtime/seat_guard.py`) refuses foreign-seat calls before dispatch, and its
docstring states plainly what it does *not* cover — "*When* an action happens —
that a seat must not advance the phase or play out of turn — is an
orchestrator-side judgement" (`seat_guard.py:62-65`). That is the largest
unenforced misbehaviour class in the system and nothing in the corpus says so.

**Growth is not free and the corpus has been growing.** The judge is single-shot:
everything selected is inlined into one system prompt against a budget derived
from the context window, **295,904 characters** at the defaults.
`marvel-champions-rules-reference` already occupies 274,874 of it, and
`services/eval-service/tests/unit/test_judge_skill_references.py:624` fails the
moment the shipped corpus stops fitting. On the agent side `MAX_INLINE_SKILLS` is
4, and the four largest `SKILL.md` files are the largest single context cost a
session pays. So "extend and improve" has to be paid for out of cuts.

## What Changes

- **`marvel-champions-play`** — the turn loop becomes a stated procedure: entry
  conditions and required inputs (seat, `session_id`, hero) that the agent must
  refuse to guess at, ordered steps each with the observation that confirms it,
  explicit stop conditions, and a failure ladder that says when to retry, when to
  report, and when to stop acting. A new guardrail section names the seat guard's
  three refusal shapes, states which misbehaviours the guard does **not** catch,
  and documents `list_my_illegal_actions` — the seat's only view of findings
  recorded against it.
- **`marvel-champions-orchestrator`** — Phase 0 gains explicit entry conditions
  and an abort; the round loop gains a per-step verification and a stop condition;
  failure handling is widened from "a seat failed" to the crash modes the runtime
  actually produces (a child that crashed, one that hit its tool-round limit, one
  that streams while stuck, one already given up on). The illegal-action findings
  loop — report from game state, never from a seat's claim; the seat performs its
  own undo; resolve only after verifying against game state — is documented for
  the first time. A trust-boundary rule states that a seat's report is data, not
  instruction.
- **`marvel-champions-learn-to-play`** — restructured from a 709-line monolith
  into a lean `SKILL.md` plus `references/`, following the progressive-disclosure
  shape every other skill in the corpus already uses. The Core-Set component
  inventory, the per-scenario encounter-set card lists, the starter-deck contents
  and the nemesis-set table are **cut**: they describe a physical box, are
  Core-Set-only (so wrong for any other scenario the plugin can load), and are
  already obtainable from `search_cards_marvel_champions`.
- **`marvel-champions-rules-reference`** — `SKILL.md` gains a stated lookup loop
  (route → load → answer → cite → stop) and a "do not answer from memory" rule
  matching the base system prompt's existing instruction. Its resources are
  untouched; the skill is the judge's rulebook and its budget headroom is 21,867
  characters.
- **`dragncards`** — gains a scope declaration. It is a plugin-authoring skill
  that happens to sit in a runtime skill root, so it is offered to the
  game-playing agent alongside the play skills; it now says in its own body that
  it is not a play skill and that DragnLang is not a way to act on a table.
- **Ancillary docs** — `services/eval-service/README.md`,
  `services/eval-service/.env.example` and
  `services/eval-service/src/eval_service/judge/skill_resources.py` carry hard-coded
  corpus byte counts that this change moves; they are updated in the same commit.

## Non-goals

- **Verifying that any of this improves play.** No provider in this environment
  reports `available: true` and bifrost holds no credentials, so no agent can be
  run. This change is verified as *loadable, in-budget and test-green* only.
  Behavioural improvement is DRA-58's job (play real games, observe, correct).
- **Enforcing turn or phase authority in code.** The seat guard deliberately
  scopes ownership and not timing. Making "played out of turn" a runtime refusal
  is a service change, not a skill change, and stays out of scope.
- **Adding a timeout or failsafe to subagent waits (DRA-51).** The skill can tell
  the orchestrator what to do when a seat stalls; it cannot stop the stall.
- **Rewriting `marvel-champions-play`'s resources.** They were checked against a
  live game two weeks ago and are the most accurate material in the corpus. Only
  `SKILL.md` changes; the resources gain cross-references and nothing else.
- **Changing the eval budget, the rubric, or any judge configuration.**
- **Renaming any skill directory.** Skill identity is the directory name, and
  `test_judge_skill_references.py` skips silently rather than failing when
  `marvel-champions-rules-reference` cannot be found.

## Impact

- Affected specs: `marvel-champions-play-skill` (loop, guardrails),
  `game-orchestration` (orchestrator loop, findings, trust boundary),
  `runtime-skill-corpus` (new — the shape contract the corpus as a whole holds to).
- Affected code: `skills/` only. No service source changes.
- Affected docs: `services/eval-service/README.md`,
  `services/eval-service/.env.example`,
  `services/eval-service/src/eval_service/judge/skill_resources.py` docstring,
  `services/agent-orchestrator/README.md` where it names skills by example.
- **Contracts that constrain the edit.** `marvel-champions-rules-reference` must
  keep at least 9 non-`SKILL.md` markdown files and its whole corpus must stay
  within 295,904 characters
  (`services/eval-service/tests/unit/test_judge_skill_references.py:624-654`).
  Frontmatter must stay parseable by the hand-rolled reader in
  `runtime/skills.py:41-79`: `---` on line 1, a single-line `description`, and
  `metadata` as a flat two-space mapping. No new symlinked or non-`.md`
  references, which both loaders drop.
- **No image rebuild is triggered by this change**, but both images bake `skills/`
  at build time, so the edits do not reach a running stack until it is rebuilt.
