## 1. Game-Service Room Module

- [x] 1.1 Introduce a Phoenix Adapter that owns room-channel event names, refs, payload construction, and raw send/wait behavior
- [x] 1.2 Introduce a room Module Interface for state refresh, stale-state recovery, action execution, room control, alerts, and GUI updates
- [x] 1.3 Refactor `SessionManager` and the HTTP/MCP adapters to delegate through the room Module Interface instead of mutating session internals directly
- [x] 1.4 Add unit tests covering room Module behavior through the new Interface without constructing raw Phoenix messages in callers
- [x] 1.5 Add integration tests covering state fetch, action execution, and representative room-control flows through the preserved HTTP surface

## 2. Game-Service Action Locality

- [x] 2.1 Consolidate generic action typing, translation, and catalog metadata into one shared action Module
- [x] 2.2 Remove duplicated player-count and other generic action translation logic from room/session code paths
- [x] 2.3 Update global and session action catalog code to derive generic action definitions from the shared action Module
- [x] 2.4 Add unit tests proving catalog generation and action execution share the same generic action definitions

## 3. Agent-Orchestrator Prompt-Run Module

- [x] 3.1 Extract a prompt-run Module from `WorkerService` that owns tool rounds, cancellation checkpoints, event emission, and terminal outcomes
- [x] 3.2 Refactor the worker loop and child-job execution path to delegate through the prompt-run Module Interface
- [x] 3.3 Add unit tests covering prompt completion, failure, and cancellation through the prompt-run Module Interface
- [x] 3.4 Add regression tests proving existing job APIs and persisted event behavior remain compatible while prompt-run ownership moves

## 4. Agent-Orchestrator Session Transcript Module

- [x] 4.1 Introduce a session transcript Module that owns replay selection, compaction checkpoint interpretation, and next-request context estimation
- [x] 4.2 Move context metadata calculation to the session transcript Module so execution and observability share one source of truth
- [x] 4.3 Refactor repository mixins and runtime helpers to become storage or helper Adapters behind the session transcript Module
- [x] 4.4 Add unit tests covering replay ordering, compaction checkpoint behavior, and bounded next-request estimates through the transcript Module Interface

## 5. Agent-Orchestrator Job Event Stream Module

- [x] 5.1 Introduce a job event stream Module that owns persisted replay, live tailing, reconnect cursors, and terminal close behavior
- [x] 5.2 Refactor the SSE router to delegate replay-plus-live delivery through the job event stream Module Interface
- [x] 5.3 Add unit tests covering replay-plus-live merge behavior, reconnect cursors, and terminal stream closure
- [x] 5.4 Add integration tests covering `GET /jobs/{job_id}/events/stream` reconnect behavior through the preserved HTTP surface

## 6. Dashboard Play Session Module

- [x] 6.1 Introduce a play session Module that owns selected-session loading, configuration sync, prompt submission, cancellation, transcript loading, and context refresh
- [x] 6.2 Refactor `PlayWorkspace` to use the play session Module Interface and remove direct orchestration logic from the view Module
- [x] 6.3 Add dashboard tests covering create/select/save/submit/cancel flows through the play session Module and preserved UI behavior

## 7. Dashboard Transcript/Event Locality

- [x] 7.1 Consolidate streamed and persisted job-event interpretation into one shared transcript/event Module
- [x] 7.2 Refactor streaming, transcript aggregation, and subagent reconciliation helpers to reuse the shared interpretation Module
- [x] 7.3 Add dashboard tests covering reconnect, chunk merge, terminal events, and subagent reconciliation without duplicate or missing transcript entries

## 8. Thin Adapter Preservation

- [x] 8.1 Audit dashboard proxy and merged OpenAPI code to ensure Play workspace orchestration state does not leak into those Adapters during refactoring
- [x] 8.2 Add or update regression tests proving proxy forwarding and merged OpenAPI generation remain independent from Play workspace state
- [x] 8.3 Remove any pass-through modules introduced during migration that do not increase Depth after the new Interfaces are in place
