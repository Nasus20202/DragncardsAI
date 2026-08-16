# Link every shipped skill to the DragncardsAI runtime reality

## Why

The repo-root `skills/` directory is a **runtime skill root**: the agent-orchestrator
enumerates it into the system prompt and the eval-service inlines selections from it into
the judge's single-shot prompt, so everything placed there is offered to the game-playing
agent as game knowledge. Today every skill in the corpus describes only the card game
itself — the Marvel Champions rules, the turn loop, the phase order. None of them names
the DragncardsAI reality the agent actually lives in: the four first-party services it can
reach, the MCP tool namespaces those services expose, and the workflow and guardrails that
constrain how a seat may use them.

DRA-63 asks for the skills to be "linked with the DragncardsAI reality — tools, MCPs etc.
Guardrails and workflow descriptions should be strict." A player agent that never sees the
service names, the tool namespaces, or the turn-order and phase rules written down will
not reliably keep them: DRA-30's seat guard refuses foreign-seat calls before dispatch,
but *when* an action happens — turn order, phase authority — is enforced nowhere and must
be carried by the skill text instead.

This change adds that meta-context as a per-skill preface file,
`DRAGNCARDSAI_REALITY.md`, in **every** skill directory under the repo-root `skills/`
catalogue. The card-game content of the skills stays byte-identical — only the
meta-context is added, in a file of its own, so the rules corpus and its reference budget
are untouched.

## What Changes

- **`skills/<skill>/DRAGNCARDSAI_REALITY.md` for every skill directory under `skills/`**
  (`dragncards`, `marvel-champions-learn-to-play`, `marvel-champions-orchestrator`,
  `marvel-champions-play`, `marvel-champions-rules-reference`). Each preface names the
  four first-party services and their purposes:
  - **game-service** — live game state, game actions, mulligan, deck-load; tools exposed
    under the `game-service_*` namespace.
  - **agent-orchestrator** — session management, prompt submission, job status/events,
    illegal-action findings; tools exposed under the `agent-orchestrator_*` namespace.
  - **eval-service** — round/game evaluation, judge communication; tools exposed under
    the `eval-service_*` namespace.
  - **history-service** — game event history, snapshots, restore; tools exposed under the
    `history-service_*` namespace.
- Each preface states the strict guardrails that hold for a seat regardless of the skill
  that loaded it:
  - a seat must not act out of turn (DRA-62/DRA-57);
  - a seat must not use tools outside its allowed set (DRA-30);
  - a seat must not advance the phase (DRA-62);
  - findings recorded via `report_illegal_action` (DRA-30) are not editable by the seat —
    the seat performs the stated undo, only the coordinating agent resolves and closes the
    finding.
- Each preface states the workflow — **spawn, observe, decide, act, report** — with each
  step naming the MCP tools available for it.
- Each preface references the skill's existing files by path (`SKILL.md`, the
  `resources/` or `references/` files) and points at where the card-game rules live; it
  does not restate them.
- **`openspec/specs/runtime-skill-corpus/spec.md`** gains a requirement: every skill
  directory in the runtime root SHALL ship a `DRAGNCARDSAI_REALITY.md` that names the
  four services, lists the MCP namespaces, states the four guardrails, and describes the
  spawn–observe–decide–act–report workflow.

### Modified Capabilities

- **`runtime-skill-corpus`** — new requirement "Every shipped skill carries a
  DragncardsAI-reality preface" covering the file's presence, contents, and the
  unchanged-skills constraint.

### Impact

- **`skills/`** — five new `DRAGNCARDSAI_REALITY.md` files; no existing skill file
  modified.
- **`openspec/specs/runtime-skill-corpus/spec.md`** — one new requirement.
- **No code changes** — no service source, no tests, no telemetry, no infra.

## Non-goals

- **No changes to the card-game content** of any `SKILL.md`, `resources/`, or
  `references/` file. The reality preface is a separate file precisely so the rules corpus
  and the judge's reference budget are untouched.
- **No changes to `.agents/skills/`** — those are assistant-facing workflow skills
  (linear-workflow, openspec-*), not runtime skills, and are out of scope.
- **No new services, ports, or dependencies.**
- **No behaviour change** in any service; this is documentation that reaches the model.
