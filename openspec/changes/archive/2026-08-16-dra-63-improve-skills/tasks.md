# Tasks

Ordered so each section is independently shippable and a partial run leaves a valid
OpenSpec tree at the end of every task.

## 1. Add the DragncardsAI-reality preface to every skill directory

- [x] 1.1 Create `skills/marvel-champions-play/DRAGNCARDSAI_REALITY.md` — names the four
      services and their purposes, lists the `game-service_*` / `agent-orchestrator_*` /
      `eval-service_*` / `history-service_*` namespaces, states the four guardrails
      (no acting out of turn, no tools outside the allowed set, no phase advancement,
      findings not editable by the seat), and the spawn–observe–decide–act–report
      workflow with the MCP tools available at each step. References `SKILL.md` and its
      `resources/` files by path. Card-game content unchanged.
- [x] 1.2 Create `skills/marvel-champions-orchestrator/DRAGNCARDSAI_REALITY.md` — same
      preface, written for the coordinating agent: it holds phase and turn authority, and
      it resolves illegal-action findings via `resolve_illegal_action`. References
      `SKILL.md` and its `references/` files by path.
- [x] 1.3 Create `skills/marvel-champions-rules-reference/DRAGNCARDSAI_REALITY.md` —
      same preface, written for a question-answering skill: it answers rules questions
      and never touches a live table. References `SKILL.md` and its `resources/` files by
      path.
- [x] 1.4 Create `skills/marvel-champions-learn-to-play/DRAGNCARDSAI_REALITY.md` — same
      preface, written for the primer: it summarises the round shape and routes to
      `marvel-champions-play` / `marvel-champions-rules-reference` for execution and
      authority. References `SKILL.md` and its `references/` files by path.
- [x] 1.5 Create `skills/dragncards/DRAGNCARDSAI_REALITY.md` — same preface, written for
      the platform skill: it is not a play skill and DragnLang is not a way to act on a
      live table. References `SKILL.md` by path.

## 2. Spec the pattern

- [x] 2.1 Add the `## ADDED Requirements` delta to
      `openspec/changes/dra-63-improve-skills/specs/runtime-skill-corpus/spec.md`: every
      skill directory in the runtime root SHALL ship a `DRAGNCARDSAI_REALITY.md` naming
      the four services, listing the MCP namespaces, stating the four guardrails and the
      spawn–observe–decide–act–report workflow, and SHALL NOT alter the card-game
      content. Include a WHEN/THEN scenario per requirement.

## 3. Verify

- [x] 3.1 `openspec validate dra-63-improve-skills` — the change validates.
- [x] 3.2 `./scripts/lint.sh` — clean (no Python changes; catches formatting issues in
      the new files if any).

## 4. Archive

- [x] 4.1 `openspec archive dra-63-improve-skills --yes` to move the change into
      `openspec/changes/archive/` and sync the `runtime-skill-corpus` delta into
      `openspec/specs/`.
- [x] 4.2 Confirm the archive directory exists and contains `proposal.md`, `tasks.md`,
      and `specs/`.
