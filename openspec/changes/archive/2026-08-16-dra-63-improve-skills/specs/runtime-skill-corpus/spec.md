## ADDED Requirements

### Requirement: Every shipped skill carries a DragncardsAI-reality preface

Every skill directory in the repo-root `skills/` catalogue SHALL ship a `DRAGNCARDSAI_REALITY.md` file. The file SHALL name the four first-party services — game-service (live game state, game actions, mulligan, deck-load), agent-orchestrator (session management, prompt submission, job status and events), eval-service (round/game evaluation, judge communication), and history-service (game event history, snapshots, restore) — and SHALL list the MCP tool namespaces each exposes (`game-service_*`, `agent-orchestrator_*`, `eval-service_*`, `history-service_*`).

The file SHALL state the guardrails that hold for a seat: a seat must not act out of turn, must not use tools outside its allowed set, must not advance the phase, and must not edit an illegal-action finding recorded against it via `report_illegal_action` — the seat performs the stated undo and only the coordinating agent resolves and closes the finding. The file SHALL describe the workflow as spawn, observe, decide, act, report, naming the MCP tools available at each step.

The preface SHALL reference the skill's existing files by path and SHALL NOT alter the card-game content of the skill's `SKILL.md`, `resources/`, or `references/` files.

The repo-root `skills/` directory is a runtime skill root: the agent-orchestrator enumerates it into the system prompt and the eval-service inlines selections from it into the judge's prompt, so everything placed there is offered to the game-playing agent as game knowledge. The reality preface is what ties that knowledge to the actual runtime the agent acts through.

#### Scenario: A skill directory in the runtime root carries the preface

- **WHEN** an agent reads a skill directory under the repo-root `skills/` catalogue
- **THEN** the directory SHALL contain a `DRAGNCARDSAI_REALITY.md` that names the four services, lists the four MCP tool namespaces, and states the four guardrails and the spawn–observe–decide–act–report workflow

#### Scenario: The preface does not touch the card-game content

- **WHEN** the `DRAGNCARDSAI_REALITY.md` file is added or updated
- **THEN** the skill's `SKILL.md` and its `resources/` and `references/` files SHALL remain unchanged
