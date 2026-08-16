# runtime-skill-corpus Specification

## Purpose

This spec defines the structural contract every skill in the repo-root `skills/`
directory must meet, independent of what any one skill teaches. That directory is a
runtime skill root: the agent-orchestrator enumerates it into the system prompt and the
eval-service inlines selections from it into the judge's single-shot prompt, so anything
placed there is offered to the game-playing agent as game knowledge.

It covers four things that hold across the corpus: that each skill declares its own scope
and names the skill owning what it excludes, that an entry point stays small and routes to
reference files rather than carrying detail, that a question-answering skill states a
lookup loop which cites its source and stops, and that the shipped rules corpus stays
within the reference budget derived from the judge's context window.

Per-skill content contracts live in their own specs -- `marvel-champions-play-skill` for
the player skill and `game-orchestration` for the orchestrator. How the budget itself is
derived belongs to `agent-move-evaluation`.

## Requirements

### Requirement: Every shipped skill declares its scope in its own body

Each `SKILL.md` under the repo-root skill directory SHALL open by stating who the skill is for and what it does not cover, SHALL name the skill that owns each subject it excludes, and a skill that is not about playing a hand of the game SHALL say so explicitly.

The repo-root `skills/` directory is a runtime skill root: the agent-orchestrator enumerates it into the system prompt and the eval-service inlines selections from it into the judge's prompt, so everything placed there is offered to the game-playing agent as though it were game knowledge.

#### Scenario: A non-play skill is identified as such

- **WHEN** an agent loads a skill in the runtime root that documents platform or plugin internals rather than play
- **THEN** the skill SHALL state that it is not a play skill and SHALL state that its platform primitives are not a way to act on a live table

#### Scenario: A skill names the skill that owns what it excludes

- **WHEN** a skill states a subject it does not cover
- **THEN** it SHALL name the skill that does cover it

### Requirement: A skill's entry point stays small and routes to its references

A `SKILL.md` that exceeds roughly five hundred lines SHALL be split, with the detail moved into reference files under the skill directory, and every reference file a skill ships SHALL be named in its `SKILL.md` together with the condition under which the agent loads it.

Reference files are fetched on demand by the agent and selected individually by the judge, whereas a `SKILL.md` body is inlined whole every time its skill is loaded or mentioned. Detail therefore belongs in references and routing belongs in the entry point.

#### Scenario: A monolithic skill is split

- **WHEN** a skill's entry point holds detail beyond what routing and the common path require
- **THEN** that detail SHALL be moved into reference files under the skill directory
- **AND** the entry point SHALL retain a routing table naming each reference and its load condition

#### Scenario: A reference is discoverable from the entry point

- **WHEN** an agent reads a skill's entry point
- **THEN** every markdown file the skill ships SHALL be findable from it without listing the directory

### Requirement: A skill that answers questions states its lookup loop

A skill whose purpose is answering rules questions SHALL state its lookup loop: how a question is routed to a reference, that errata is applied to any named card before the rest of the answer is composed, that the answer cites the rule or glossary entry it came from, and that the loop then stops. It SHALL state that answers are composed from loaded references rather than recalled from memory, SHALL forbid loading references speculatively, and SHALL require an unanswerable question to be reported as unanswerable.

#### Scenario: A question names a card with errata

- **WHEN** a rules question names a specific card
- **THEN** the skill SHALL route the errata reference first and SHALL apply corrected text before answering

#### Scenario: A question cannot be answered from the references

- **WHEN** no loaded reference settles the question
- **THEN** the skill SHALL instruct the agent to say so rather than compose an answer from recollection

### Requirement: The shipped rules corpus stays within the judge's derived reference budget

The rules reference skill SHALL remain selectable in full: its `SKILL.md` together with every reference file it ships SHALL fit the reference budget derived at the default judge configuration, and it SHALL keep enough separate reference files that a judge can select a subset of the rulebook rather than all or none.

The judge is single-shot: every selected skill and reference is inlined into one prompt, the budget for that content is derived from the judge's context window, and a selection that exceeds it is refused rather than truncated.

#### Scenario: The whole rules corpus is selectable

- **WHEN** a judge configuration selects the rules reference skill and every one of its reference files at the default context window
- **THEN** the selection SHALL be accepted and no reference SHALL be refused for exceeding the budget

#### Scenario: Growth in the entry point costs reference headroom

- **WHEN** content is added to a skill's `SKILL.md`
- **THEN** the available reference budget SHALL fall by the same amount, because a selected `SKILL.md` is charged against the budget before references are measured

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
