## ADDED Requirements

### Requirement: Crashed prompt runs reach a terminal status
The worker SHALL drive every claimed prompt job to a terminal status no matter which error is raised while executing it. This includes error types the worker does not explicitly classify — for example timeouts, `ExceptionGroup` wrappers raised by task groups, and programming errors — and errors raised before the first model call, such as while loading the job, reading its model configuration, or checking for cancellation.

Any such error SHALL be classified, persisted as a `failure` event, and applied through job failure handling so the job ends as `"failed"` (or is re-queued when the classified failure is retryable and attempts remain). A prompt job SHALL NOT be left in the non-terminal `"running"` status because of an unhandled error. `asyncio.CancelledError` SHALL remain uncaught so worker shutdown continues to cancel in-flight jobs.

When the prompt run's own failure handling raises, the worker SHALL still mark the job `"failed"` with `error_code = "worker_crash"`.

Because context replay only includes `"completed"`, `"interrupted"`, and `"failed"` jobs, reaching a terminal status is what keeps the prompt of a crashed run in the session transcript, so the next run replays that prompt instead of continuing as though the message was never sent.

#### Scenario: Unclassified error during the model call
- **WHEN** the gateway call for a prompt job raises an error the worker does not explicitly classify, such as a timeout or an `ExceptionGroup`
- **THEN** the worker SHALL persist a `failure` event for the job
- **AND** the job SHALL end with status `"failed"` rather than remaining `"running"`

#### Scenario: Error before the first model call
- **WHEN** a prompt job crashes before its first model call, for example while checking cancellation or loading the job record
- **THEN** the job SHALL end with status `"failed"` rather than remaining `"running"`

#### Scenario: Failure handling itself crashes
- **WHEN** the prompt run raises while recording a failure, so the exception escapes the prompt run
- **THEN** the worker SHALL mark the job `"failed"` with `error_code = "worker_crash"`

#### Scenario: The prompt of a crashed run survives into the next run
- **WHEN** a prompt job crashes and a later job runs in the same session with `multi_turn_memory` enabled
- **THEN** the crashed job's prompt SHALL appear as a `role: user` message in the replayed context
- **AND** SHALL be followed by the synthetic assistant note for failed jobs
