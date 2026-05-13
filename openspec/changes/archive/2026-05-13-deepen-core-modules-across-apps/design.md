## Context

The current codebase exposes stable external behavior through several shallow internal Modules.

- In `game-service`, room semantics are split across `GameSession`, `SessionManager`, raw Phoenix protocol calls, and duplicated action translation logic. Callers must understand transport details to reason about room behavior.
- In `agent-orchestrator`, `WorkerService` owns nearly the full prompt-run lifecycle, while replay, compaction, token accounting, and event streaming are split across repository mixins, runtime helpers, and router code.
- In `dashboard`, `PlayWorkspace` owns session lifecycle, configuration sync, prompt submission, cancellation, job loading, and stream reconciliation directly, while transcript semantics are duplicated across several helpers.
- By contrast, dashboard proxy forwarding and merged OpenAPI generation are already thin Adapters with one real responsibility each.

The goal of this change is to increase Depth at the Interfaces for room behavior, prompt execution, transcript construction, and Play workspace orchestration. The change must preserve the existing HTTP, MCP, and dashboard-visible behavior while improving Locality and testability behind those Interfaces.

Stakeholders are maintainers working in the three apps, dashboard users relying on stable behavior, and AI agents navigating the repo. We do not control upstream DragnCards Phoenix behavior, so any new Seam must keep that risk concentrated behind an Adapter.

## Goals / Non-Goals

**Goals:**
- Deepen the `game-service` room Module so room semantics are owned at one Interface and Phoenix protocol knowledge moves behind an Adapter
- Keep generic game action typing, translation, and catalog metadata in one place so global and session action behavior share one source of truth
- Deepen `agent-orchestrator` prompt execution into one prompt-run Module with strong Locality for cancellation, tool rounds, event emission, and terminal outcomes
- Deepen `agent-orchestrator` session transcript construction so replay, compaction checkpoints, and next-request context estimation share one Interface
- Deepen `agent-orchestrator` job event streaming so replay-plus-live delivery is owned by one Module rather than inline router logic
- Deepen dashboard Play workspace orchestration behind one play session Module while leaving React view Modules thin
- Remove duplicated stream and transcript semantics from dashboard helpers so the dashboard consumes orchestrator-owned behavior through a smaller Interface
- Keep proxy and merged OpenAPI code thin on purpose and prevent unrelated play-session logic from leaking into them

**Non-Goals:**
- Changing public route names, MCP tool names, payload shapes, or dashboard layout as the primary outcome of this change
- Replacing Phoenix Channels, Bifrost, Valkey, or HeroUI
- Introducing speculative cross-process abstractions shared between Python and TypeScript implementations
- Deepening dashboard proxy or OpenAPI code before a second real Adapter exists
- Solving every legacy naming or file-layout issue unrelated to the target deep Modules

## Decisions

### D1: Deepen a room Module in `game-service` and move Phoenix protocol knowledge behind an Adapter

**Decision**: Create a room-facing Interface that owns state refresh, stale-state recovery, room control, alert buffering, GUI update buffering, and action execution semantics. Raw Phoenix event names, refs, payload construction, and send/wait mechanics move behind a Phoenix Adapter at the Seam.

**Alternatives considered**:
- *Keep `GameSession` and `SessionManager` mostly as-is and only extract more helpers*: rejected because it preserves the current shallow split and does not improve Locality.
- *Expose Phoenix client primitives directly to higher-level callers*: rejected because it widens the Interface and leaks upstream protocol details everywhere.
- *Create separate Modules for each room-control operation*: rejected because it would produce more shallow Modules around one domain concept.

**Rationale**: The room is the core domain concept in `game-service`. A deeper room Module gives callers high Leverage and keeps Phoenix volatility behind one Adapter.

### D2: Keep generic game actions as one concentrated Module, but make it internal to the room Module rather than a new top-level Seam

**Decision**: Consolidate generic game action typing, translation, and catalog metadata so the room Module and action catalog both depend on one action definition source. This remains an internal Module supporting the room Interface rather than a separate top-level Interface.

**Alternatives considered**:
- *Promote game actions to a separate top-level capability with its own public Seam*: rejected because there is not yet a second real Adapter that justifies the extra Seam.
- *Leave catalog and execution translations split across files*: rejected because duplication, especially around player-count changes, keeps the action concept shallow.

**Rationale**: This concentrates the Implementation of one concept without creating a speculative new Interface.

### D3: Deepen prompt execution in `agent-orchestrator` into a prompt-run Module

**Decision**: Move prompt execution out of `WorkerService._run_job` into one prompt-run Module whose Interface owns tool rounds, cancellation checkpoints, event emission, and terminal job outcomes. The worker loop remains responsible for claiming work and delegating execution.

**Alternatives considered**:
- *Keep `_run_job` as the main coordinator and only split out more tiny helpers*: rejected because it improves file size but not Depth.
- *Move all orchestration into repositories*: rejected because repositories should not own runtime coordination semantics.
- *Split prompt execution into many peer Modules immediately*: rejected because the first need is one deeper Interface, not more surface area.

**Rationale**: Prompt execution is a real domain concept with many callers and tests. Concentrating it behind one Interface increases Locality and makes failure handling coherent.

### D4: Make session transcript construction the source of truth for replay, compaction checkpoints, and next-request context estimation

**Decision**: Introduce a session transcript Module that owns replay selection, compaction checkpoint interpretation, and the token-estimation view of what the next request will include. Storage becomes an Adapter behind that Module.

**Alternatives considered**:
- *Keep transcript rules split between repository mixins and runtime helpers*: rejected because the same concept remains spread across multiple shallow Modules.
- *Let the context metadata endpoint build its own estimate separately*: rejected because it creates divergent semantics between execution and observability.
- *Fold stream delivery into transcript ownership*: rejected because delivery semantics have a distinct Interface and lifecycle.

**Rationale**: Replay and context accounting are one concept from the caller's perspective: what prior context the next prompt sees.

### D5: Deepen job event streaming into its own Module rather than leaving merge logic in the router

**Decision**: Introduce a job event stream Module that owns persisted replay, live tailing, reconnect cursors, and terminal close behavior. The SSE router becomes a thin Adapter over that Interface.

**Alternatives considered**:
- *Keep replay-plus-live merge logic inline in the API router*: rejected because it leaves event delivery shallow and hard to test.
- *Push replay semantics entirely into the live event bus*: rejected because persisted replay and HTTP stream lifecycle do not belong to the same Adapter.
- *Let the dashboard own more reconciliation logic*: rejected because it spreads one concept across apps.

**Rationale**: Event delivery has a distinct Interface from transcript construction. Separating it preserves Depth in both Modules.

### D6: Deepen dashboard Play workspace orchestration into one play session Module and keep UI Modules thin

**Decision**: Introduce a play session Module in the dashboard that owns selected-session loading, configuration sync, prompt submission, cancellation, transcript loading, stream attachment, and context refresh. `PlayWorkspace` and related React Modules become presentation Adapters over that Interface.

**Alternatives considered**:
- *Keep `PlayWorkspace` as the orchestration owner*: rejected because the current Interface is too broad and the Implementation is the dashboard's main source of Locality loss.
- *Split behavior across many unrelated hooks immediately*: rejected because it risks trading one god Module for many shallow Modules.

**Rationale**: The play session is the dashboard's core domain concept. A deeper Module reduces React-specific incidental complexity at the seam.

### D7: Centralize dashboard transcript/event interpretation and keep proxy/OpenAPI intentionally thin

**Decision**: Consolidate dashboard transcript and stream interpretation into one shared Module that consumes orchestrator event semantics. Do not deepen proxy forwarding or merged OpenAPI beyond their current Adapter role.

**Alternatives considered**:
- *Leave transcript semantics spread across `use-job-streaming`, `job-events`, and `transcript`*: rejected because it duplicates execution semantics already owned by the orchestrator domain.
- *Deepen proxy/OpenAPI now as part of the same effort*: rejected because there is still only one real variation path, so the Seam would remain hypothetical.

**Rationale**: Candidate 7 is worth fixing because it improves Locality in a real domain concept. Candidate 8 is worth preserving as thin because more abstraction there would not buy Leverage yet.

### D8: Preserve external behavior while moving internal Seams

**Decision**: The refactor will preserve existing HTTP routes, MCP tools, SSE endpoints, and dashboard-visible interaction flows unless a narrower Interface requires a small compatibility shim during migration.

**Alternatives considered**:
- *Change external APIs while deepening Modules*: rejected because it couples architectural cleanup to unnecessary client migration.
- *Delay tests until after the refactor settles*: rejected because the Interface is the test surface and must be protected during the move.

**Rationale**: The value of the refactor is better Locality and Leverage without external churn.

## Risks / Trade-offs

- **[Risk] DragnCards Phoenix behavior remains outside our control** → Mitigation: keep Phoenix event names, refs, and payload construction behind one Adapter and add targeted integration tests around room behavior.
- **[Risk] Temporary parallel code paths could reduce clarity during migration** → Mitigation: migrate one deep Module at a time and remove pass-through layers immediately after delegation is complete.
- **[Risk] Transcript and stream Modules may still share subtle assumptions about event ordering** → Mitigation: add shared fixtures and explicit reconnect/terminal tests at the new Interfaces.
- **[Risk] Dashboard behavior could regress if Play workspace orchestration moves without enough contract tests** → Mitigation: preserve user-visible flows with play session Module tests and view-level smoke tests.
- **[Risk] Keeping proxy/OpenAPI thin may feel inconsistent next to other refactors** → Mitigation: document that this is intentional because one Adapter means a hypothetical Seam, not a real one.

## Migration Plan

- Refactor `game-service` first: introduce the Phoenix Adapter and room Interface, then move action locality into the shared action Module and remove duplicated translations.
- Refactor `agent-orchestrator` next in two passes: first prompt-run ownership, then session transcript and job event stream ownership, keeping SSE and job APIs stable throughout.
- Refactor dashboard last: introduce the play session Module, collapse transcript helpers into one event-interpretation Module, and leave proxy/OpenAPI behavior unchanged except for regression coverage.
- Roll back by reverting delegation to the new deep Modules while preserving external routes and payloads; all schema and API changes in this change are architectural and do not require destructive data rollback.

## Open Questions

- Whether the `game-service` action Module should remain fully internal forever or later become a real Seam if a second Adapter appears
- Whether the dashboard will eventually need a second consumer of merged OpenAPI or proxy policy that would justify deepening those Adapters later
