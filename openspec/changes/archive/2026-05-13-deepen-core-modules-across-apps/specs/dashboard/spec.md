## ADDED Requirements

### Requirement: Play workspace orchestration is owned by one play session Module
The dashboard SHALL concentrate selected-session loading, configuration sync, prompt submission, cancellation, transcript loading, and context refresh behind one play session Module Interface.

React view Modules in the Play workspace SHALL act as Adapters over that Interface rather than owning orchestration behavior directly.

#### Scenario: Play workspace delegates session lifecycle behavior
- **WHEN** the user creates, selects, updates, compacts, submits a prompt for, or cancels execution in a session
- **THEN** the Play workspace SHALL delegate that orchestration behavior through the same play session Module Interface

#### Scenario: Play session Module reconciles history load and stream attachment
- **WHEN** a selected session reloads while its newest job is queued or running
- **THEN** the play session Module SHALL reconcile transcript history loading and stream attachment
- **AND** SHALL preserve one sorted jobs view for the session

### Requirement: Dashboard transcript rendering consumes one shared event interpretation Module
The dashboard SHALL interpret streamed and persisted orchestrator job events through one shared transcript/event Module rather than reimplementing terminal, chunk-merge, and subagent reconciliation rules across multiple helpers.

#### Scenario: Transcript helpers share one interpretation path
- **WHEN** job events update model output, reasoning, tool calls, tool results, compaction state, or subagent state
- **THEN** the dashboard SHALL apply those event types through one shared transcript/event interpretation Module

#### Scenario: Reconnect behavior matches orchestrator stream semantics
- **WHEN** the dashboard reconnects to an in-progress job
- **THEN** the dashboard transcript/event Module SHALL reuse orchestrator-compatible cursor and snapshot rules
- **AND** SHALL render the transcript without duplicate or missing events

### Requirement: Proxy and merged OpenAPI remain thin Adapters
The dashboard SHALL keep proxy forwarding and merged OpenAPI generation independent from Play workspace orchestration state.

#### Scenario: Proxy behavior ignores play session state
- **WHEN** a Play session is selected, running, cancelled, or terminated
- **THEN** proxy request forwarding SHALL continue to depend only on configured upstream service settings and the incoming request

#### Scenario: Merged OpenAPI generation ignores play session state
- **WHEN** the dashboard builds or serves the merged OpenAPI document
- **THEN** the merged document and any upstream fetch errors SHALL be derived only from configured upstream documents
- **AND** SHALL NOT depend on Play workspace state
