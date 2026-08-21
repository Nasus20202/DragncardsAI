# Runtime Skill Corpus

## ADDED Requirements

### Requirement: The Marvel Champions rules corpus stays platform-neutral and single-sourced

The Marvel Champions rules and strategy content in the runtime skill root SHALL contain no platform-specific token — no platform name, no tool name, no group identifier, no step identifier, and no wire format — and SHALL exist exactly once for all platforms. Adding a platform SHALL NOT add a copy of any rules or strategy reference, and SHALL NOT introduce a per-platform variant of one.

The corpus is what makes the agent able to play the game at all, and it is the largest thing the repository ships to the runtime. A second copy of it would double the content the judge's reference budget is measured against and would guarantee that the two copies diverge, so a rule fixed in one platform's copy would stay wrong in the other's. Rules are a property of Marvel Champions, not of the software the game is played through.

#### Scenario: Adding a platform adds no rules content

- **WHEN** a second game platform is supported
- **THEN** the rules reference and learn-to-play skills SHALL be unchanged
- **AND** no per-platform copy or variant of any rules or strategy reference SHALL exist in the runtime skill root

#### Scenario: A rules correction lands once

- **WHEN** a rule or an erratum is corrected in the corpus
- **THEN** the correction SHALL apply to every platform without a second edit

#### Scenario: A platform token in the rules corpus is a defect

- **WHEN** a rules or strategy reference is inspected
- **THEN** it SHALL name no platform, no tool, no group identifier, and no wire format

### Requirement: The harness contract is stated per platform, outside the neutral skill body

A skill that teaches an agent how to act on a live table SHALL state its harness contract — how state is read, how a move is expressed, how a failure is observed, and what the harness does and does not enforce — in a reference file belonging to one platform, and SHALL keep its own body platform-neutral. The neutral body SHALL route to exactly one harness reference per platform, naming each and the condition under which it is loaded, and SHALL instruct the agent to load only the reference for the platform its session is bound to.

The neutral body SHALL NOT carry conditional prose that branches on the platform inside an instruction. A procedure's authority comes from being unambiguous at the point of action, and "if one platform, otherwise the other" inside every recipe destroys that, while also charging every session for the other platform's contract in a body that is inlined whole on every load.

Where the platforms differ in what is enforced rather than only in how a move is spelled, the harness reference SHALL say so explicitly, because an agent that believes a rule is enforced treats a silent success as permission.

#### Scenario: A play skill routes to one harness reference per platform

- **WHEN** an agent reads a play skill's entry point
- **THEN** it SHALL find one harness reference per supported platform, each named with its load condition

#### Scenario: The neutral body holds no platform branch

- **WHEN** a play skill's body is inspected
- **THEN** no instruction in it SHALL be conditional on which platform the session runs

#### Scenario: A harness reference states what its platform enforces

- **WHEN** an agent loads a platform's harness reference
- **THEN** it SHALL state which rules of play that platform enforces and which it does not

### Requirement: The runtime skill root ships one platform-build skill per supported platform

The runtime skill root SHALL contain one platform-build skill per supported game platform, documenting that platform's own internals — its transport, its data formats, its configuration, and its repository layout — and SHALL keep `skills/dragncards/` and add `skills/marvel-lcg/` for the second platform. Each SHALL declare that it is not a play skill and that its platform primitives are not a way to act on a live table, and SHALL name the play skill that owns playing a hand.

A platform-build skill SHALL contain no Marvel Champions rules content, and SHALL name the shared rules skill as the owner of that subject. A marvel-lcg platform-build skill SHALL additionally state the hazards a client of that platform faces — that its engine retries invalid input without bound, that its move submission acknowledges without reporting validity, that its debug endpoint reaches arbitrary code execution and is never to be reached, and that its card scripts are executable Python so third-party card packs are never loaded.

#### Scenario: Each platform has its own build skill

- **WHEN** the skill catalogue is listed
- **THEN** `dragncards` and `marvel-lcg` SHALL both appear as platform-build skills

#### Scenario: A platform-build skill disclaims play

- **WHEN** an agent loads a platform-build skill
- **THEN** it SHALL state that it is not a play skill, SHALL state that its primitives are not a way to act on a live table, and SHALL name the skill that owns playing a hand

#### Scenario: The marvel-lcg build skill states its hazards

- **WHEN** an agent loads the marvel-lcg platform-build skill
- **THEN** it SHALL state the unbounded input-retry behaviour, the unacknowledged move submission, the prohibition on reaching the debug endpoint, and the prohibition on loading third-party card scripts

### Requirement: A skill change reaches the runtime only through an image rebuild

The runtime skill root SHALL be packaged into the agent-orchestrator and eval-service container images rather than mounted from the host at run time, and any change to a skill SHALL therefore require those images to be rebuilt before it reaches a running agent or judge. Any procedure that changes the corpus SHALL state the rebuild as a step, and SHALL NOT describe editing a skill file as sufficient on its own.

Both images copy the corpus at build time and no compose service bind-mounts it, so an edited skill file on the host is invisible to a running container. Treating an edit as live is the failure this exists to prevent: the agent keeps following the previous instructions while the file on disk says otherwise, and the resulting behaviour matches neither the spec nor the file.

#### Scenario: An edited skill does not change a running agent

- **WHEN** a skill file is edited without rebuilding the images
- **THEN** a running agent-orchestrator and eval-service SHALL still serve the previously packaged content

#### Scenario: A corpus change states its rebuild

- **WHEN** a change modifies the runtime skill root
- **THEN** its tasks SHALL include rebuilding the agent-orchestrator and eval-service images before the change is verified end to end

## MODIFIED Requirements

### Requirement: Every shipped skill carries a DragncardsAI-reality preface

Every skill directory in the repo-root `skills/` catalogue SHALL ship a `DRAGNCARDSAI_REALITY.md` file. The file SHALL name the four first-party services — game-service (live game state, game actions, mulligan, deck-load), agent-orchestrator (session management, prompt submission, job status and events), eval-service (round/game evaluation, judge communication), and history-service (game event history, snapshots, restore) — and SHALL list the MCP tool namespaces each exposes (`game-service_*`, `agent-orchestrator_*`, `eval-service_*`, `history-service_*`).

The file SHALL state that more than one game platform exists behind game-service, SHALL name every supported platform and its slug, SHALL state that a session is bound to exactly one of them, and SHALL state that the platform decides how state is read, how a move is expressed, and which rules of play are enforced. It SHALL name the platform-build skill and the harness reference that own each platform's contract, and SHALL NOT present any one platform's transport, group vocabulary, step identifiers, or tool names as the way the system works. The four services and the four MCP namespaces are not per-platform and SHALL continue to be stated once.

The file SHALL state the guardrails that hold for a seat: a seat must not act when the game is not asking that seat, must not use tools outside its allowed set, must not advance the phase or the turn on a platform where advancing is a call it holds, and must not edit an illegal-action finding recorded against it via `report_illegal_action` — the seat performs the stated undo and only the coordinating agent resolves and closes the finding. The file SHALL describe the workflow as spawn, observe, decide, act, report, naming the MCP tools available at each step and stating which of them are platform-specific.

The preface SHALL reference the skill's existing files by path and SHALL NOT alter the card-game content of the skill's `SKILL.md`, `resources/`, or `references/` files.

The repo-root `skills/` directory is a runtime skill root: the agent-orchestrator enumerates it into the system prompt and the eval-service inlines selections from it into the judge's prompt, so everything placed there is offered to the game-playing agent as game knowledge. The reality preface is what ties that knowledge to the actual runtime the agent acts through, and a preface that describes one platform as though it were the only one misdescribes that runtime for every session on the other.

#### Scenario: A skill directory in the runtime root carries the preface

- **WHEN** an agent reads a skill directory under the repo-root `skills/` catalogue
- **THEN** the directory SHALL contain a `DRAGNCARDSAI_REALITY.md` that names the four services, lists the four MCP tool namespaces, and states the four guardrails and the spawn–observe–decide–act–report workflow

#### Scenario: The preface names every supported platform

- **WHEN** an agent reads the preface
- **THEN** it SHALL name every supported platform and its slug, SHALL state that a session is bound to exactly one, and SHALL name where each platform's harness contract is documented

#### Scenario: The preface presents no platform as the only one

- **WHEN** the preface describes reading state or making a move
- **THEN** it SHALL NOT present one platform's transport, group vocabulary, step identifiers, or tool names as the system's own

#### Scenario: The preface does not touch the card-game content

- **WHEN** the `DRAGNCARDSAI_REALITY.md` file is added or updated
- **THEN** the skill's `SKILL.md` and its `resources/` and `references/` files SHALL remain unchanged

### Requirement: The shipped rules corpus stays within the judge's derived reference budget

The rules reference skill SHALL remain selectable in full: its `SKILL.md` together with every reference file it ships SHALL fit the reference budget derived at the default judge configuration, and it SHALL keep enough separate reference files that a judge can select a subset of the rulebook rather than all or none.

The judge is single-shot: every selected skill and reference is inlined into one prompt, the budget for that content is derived from the judge's context window, and a selection that exceeds it is refused rather than truncated.

Splitting a skill's harness contract into one reference per platform SHALL NOT grow what a single selection costs. A per-platform reference SHALL be selectable on its own, so a judge evaluating a game on one platform SHALL be able to select that platform's harness reference without also charging the budget for the other platform's.

#### Scenario: The whole rules corpus is selectable

- **WHEN** a judge configuration selects the rules reference skill and every one of its reference files at the default context window
- **THEN** the selection SHALL be accepted and no reference SHALL be refused for exceeding the budget

#### Scenario: Growth in the entry point costs reference headroom

- **WHEN** content is added to a skill's `SKILL.md`
- **THEN** the available reference budget SHALL fall by the same amount, because a selected `SKILL.md` is charged against the budget before references are measured

#### Scenario: One platform's harness reference is selectable alone

- **WHEN** a judge configuration selects the play skill and one platform's harness reference
- **THEN** the other platform's harness reference SHALL NOT be charged against the budget
