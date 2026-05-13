## ADDED Requirements

### Requirement: Prompt execution is owned by one prompt-run Module
The agent-orchestrator SHALL execute each prompt job through one prompt-run Module whose Interface owns tool rounds, cancellation checkpoints, event emission, and terminal job outcomes.

The worker loop SHALL remain responsible for claiming work and delegating execution, but SHALL NOT duplicate prompt-run lifecycle semantics outside that Module.

#### Scenario: Worker loop delegates prompt execution
- **WHEN** a queued prompt job or queued child prompt job is claimed for execution
- **THEN** the worker loop SHALL delegate execution through the same prompt-run Module Interface

#### Scenario: Prompt-run Module owns terminal job handling
- **WHEN** prompt execution completes, fails, or is cancelled
- **THEN** the prompt-run Module SHALL emit the final orchestration events and terminal job outcome through one Implementation path

### Requirement: Session transcript construction has one source of truth
The agent-orchestrator SHALL construct replay history, compaction checkpoint interpretation, and next-request context estimation from one session transcript Module.

#### Scenario: Worker and context metadata share transcript rules
- **WHEN** the worker builds the next model request and the context metadata endpoint estimates the next request envelope
- **THEN** both flows SHALL use the same session transcript Module Interface
- **AND** SHALL apply the same replay, compaction, and retained-tool semantics

#### Scenario: Compaction checkpoints are owned by the transcript Module
- **WHEN** the system creates or reads a compaction checkpoint for a session
- **THEN** the session transcript Module SHALL own the checkpoint semantics used to decide later replay eligibility

### Requirement: Job event streaming owns replay-plus-live delivery
The agent-orchestrator SHALL deliver job event streams through one job event stream Module that owns persisted replay, live tailing, reconnect cursors, and terminal close behavior.

#### Scenario: SSE adapter delegates replay-plus-live delivery
- **WHEN** a client subscribes or reconnects to `GET /jobs/{job_id}/events/stream`
- **THEN** the API adapter SHALL delegate replay-plus-live delivery through the same job event stream Module Interface

#### Scenario: Stream closes only after replay and live tail are reconciled
- **WHEN** a job reaches a terminal state while a client is streaming events
- **THEN** the job event stream Module SHALL deliver any remaining persisted or live events required by the stream contract before closing the stream
