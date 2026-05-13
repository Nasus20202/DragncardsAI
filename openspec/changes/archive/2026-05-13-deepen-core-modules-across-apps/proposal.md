## Why

The three main applications currently expose important domain concepts through shallow Modules whose Interfaces leak transport, persistence, and UI orchestration details. That lowers Locality, makes tests target the wrong seam, and forces both maintainers and AI agents to bounce across too many files to understand one concept.

## What Changes

- Deepen the `game-service` room Module so room semantics own state refresh, recovery, room control, and buffered room signals while Phoenix protocol details move behind an Adapter
- Concentrate generic game action typing, translation, and catalog metadata so action behavior is defined once instead of being duplicated across session and API layers
- Deepen `agent-orchestrator` prompt execution into a prompt-run Module that owns tool rounds, cancellation handling, event emission, and terminal job outcomes
- Deepen `agent-orchestrator` session transcript construction so replay selection, compaction checkpoints, and context token accounting come from one Module
- Deepen `agent-orchestrator` job event streaming so replay-plus-live delivery and terminal close behavior are owned behind one stream Module instead of inline router logic
- Deepen the dashboard Play workspace so session lifecycle, configuration sync, prompt submission, cancellation, and transcript loading move behind a play session Module
- Remove duplicated execution semantics from dashboard transcript helpers so the dashboard consumes orchestrator-owned stream and transcript behavior instead of reconstructing it piecemeal
- Keep dashboard proxy and merged OpenAPI code intentionally thin as Adapters, and prevent play-workspace orchestration concerns from leaking into them
- Preserve existing external HTTP, MCP, and dashboard user-facing behavior unless a narrower Interface is required to support the refactor safely

## Capabilities

### New Capabilities

### Modified Capabilities
- `game-service`: add architectural requirements that concentrate room semantics and generic action definitions behind deeper Modules while preserving the existing HTTP and MCP surface
- `agent-orchestrator`: add architectural requirements that concentrate prompt execution, session transcript construction, and job event streaming behind deeper Modules while preserving existing session and job APIs
- `dashboard`: add architectural requirements that move Play workspace orchestration behind a deeper Module, stop duplicating orchestrator stream semantics in UI helpers, and keep proxy and Swagger code as thin Adapters

## Non-Goals

- Changing the public HTTP routes, MCP tool names, or dashboard information architecture as a primary goal of this change
- Replacing the Phoenix transport, DragnCards integration contract, or upstream plugin behavior
- Introducing speculative new seams where only one Adapter exists and no real variation is present
- Redesigning the dashboard visual language or replacing HeroUI controls
- Collapsing all refactors into one giant shared library across Python and TypeScript codebases

## Impact

- **game-service**: `logic/session.py`, `logic/session_manager.py`, `logic/actions.py`, related API catalog code, and tests around room behavior and action definition locality
- **agent-orchestrator**: `runtime/worker.py`, `runtime/memory.py`, `runtime/compaction.py`, `runtime/live_events.py`, router code, repository composition, and tests around prompt runs, transcript construction, and stream delivery
- **dashboard**: `features/play/components/play-workspace.tsx`, play-session helpers, transcript/stream helpers, and tests around session lifecycle orchestration and transcript rendering
- **tests**: shift verification toward the deepened Module Interfaces so transport details, repository mixins, and large UI compositions stop being the default test surface
