## ADDED Requirements

### Requirement: Publishing a live job event is best-effort against its durable row
Publishing to the live job-event bus SHALL NOT be able to fail its caller. A transport
failure while publishing SHALL be logged and SHALL return no event, and the caller
SHALL proceed as though the publish had succeeded.

This is safe because of an invariant the job runtime already maintains: every event it
publishes has first been written to `job_events` in PostgreSQL, and the job event
stream polls that table as well as forwarding the live bus. A failed publish therefore
delays an event to the stream's next poll rather than losing it. The durable row is the
source of truth and the live bus is a latency optimisation, so the bus SHALL NOT be
able to cost a job its run.

Because a publish is issued once per streaming model delta, and each publish sits
inside the block whose handler marks the job failed, an unguarded publish made every
delta a chance to kill an otherwise healthy job — which is what DRA-42 reported as
orchestrator mode failing.

The tolerance SHALL be structural rather than per-call-site: the bus handed to the job
runtime SHALL be best-effort however that runtime was constructed, not only when it is
assembled by the application factory.

The scope of the tolerance SHALL be exactly this: publishing to the live bus. Writes to
PostgreSQL SHALL continue to raise, `append_event` included, since the durable row is
the thing being relied upon. `asyncio.CancelledError` SHALL NOT be caught, so worker
shutdown continues to cancel in-flight jobs.

One published event has no durable twin — the `compaction` summary, whose durable home
is the compaction job created alongside it rather than a row on the job being
compacted. Dropping its live copy SHALL be tolerated on the same terms: the running
transcript then shows the summary only after the session is reloaded, which is a
smaller loss than failing a job mid-compaction, and the drop SHALL be logged.

#### Scenario: A failed publish during a streaming delta does not fail the job
- **WHEN** every live publish raises a connection error while a prompt job streams a model response
- **THEN** the job SHALL reach status `"completed"` with its result text intact
- **AND** the `model_output` and `completion` events SHALL still be present as durable job events

#### Scenario: A publish failure is reported, not hidden
- **WHEN** a live publish fails
- **THEN** the service SHALL log the failure, naming the event type and the job

#### Scenario: A failing durable write still fails
- **WHEN** appending a job event to PostgreSQL raises
- **THEN** the error SHALL propagate to existing job failure handling rather than being tolerated

### Requirement: The job event stream degrades to durable polling when the live bus fails
A transport failure while reading the live event bus SHALL NOT terminate a job event
stream. The stream SHALL continue serving durable events from `list_events`, SHALL
retry the live bus, and SHALL resume live delivery once a read succeeds.

Propagating such a failure ended the streaming HTTP response, which surfaced to the
browser as `GET /jobs/{job_id}/events/stream` returning 500 and the live transcript
stopping mid-run (DRA-42). Since `list_events` yields every durable event, a client on
a degraded stream loses delivery latency and nothing else.

A live-bus failure SHALL be handled the same way a subscriber timeout is handled, so a
job that reaches a terminal status while the bus is unavailable SHALL still have its
remaining durable events delivered and its stream closed, rather than being left open.

While degraded, the retry delay SHALL be short enough that the durable poll — then the
stream's only source — keeps the transcript current, SHALL grow with consecutive
failures so a sustained outage is bounded in cost, SHALL be capped below the interval a
healthy stream blocks for so that degrading never increases latency, and SHALL be reset
by the first successful live read so a recovered stream returns to its normal, cheap
idle behaviour.

The retry SHALL reuse the existing subscriber rather than replacing it. A subscriber's
stream cursor advances only on a successful read, so retrying resumes exactly where it
stopped, whereas a replacement would restart from the beginning of the retained stream
and re-deliver events the client already has.

Backoff and failure counting for a degraded stream SHALL live with that stream and be
discarded when it ends. No shared or module-level registry SHALL be introduced.

#### Scenario: Durable events keep arriving while the live bus is down
- **WHEN** every live-bus read for a streaming client raises a connection error
- **THEN** the stream SHALL keep yielding events appended to `job_events`
- **AND** SHALL NOT raise out of the response

#### Scenario: A terminal job still closes a degraded stream
- **WHEN** a job reaches a terminal status while the live bus is unavailable
- **THEN** the stream SHALL deliver the remaining durable events and close

#### Scenario: Live delivery resumes after recovery
- **WHEN** the live bus fails and then succeeds for a stream that is still open
- **THEN** subsequently published events SHALL be delivered live again

### Requirement: A subagent wait falls back to the child's row when the live bus fails
A transport failure while consuming a child job's live events SHALL NOT propagate out
of a subagent wait. The wait SHALL fall back to re-reading the child's persisted row,
SHALL retry the live bus on a bounded backoff, and SHALL remain bounded by the same
absolute deadline.

The child's persisted status is already the authority for this wait; live events are
consumed only so the wait can return the moment the child finishes rather than on the
next poll. Losing them therefore costs the wait its early return and nothing else.
Before DRA-42 that read was unguarded, so a reset on a *child's* event stream escaped
`wait_for_subagent` and the tool dispatch and reached the *parent* job's failure
handler — a blip on one job's stream failing a different job, on the orchestrated
multi-agent path the issue was reported against.

#### Scenario: The child's live stream fails for the whole wait
- **WHEN** every live-bus read fails while a parent waits for a child, and the child then reaches `"completed"`
- **THEN** the wait SHALL return a `completed` outcome carrying the child's result
- **AND** SHALL NOT raise into the parent job

#### Scenario: The wait is still bounded
- **WHEN** the live bus fails repeatedly and the child never reaches a terminal status
- **THEN** the wait SHALL still end at its absolute deadline with a `timeout` outcome

### Requirement: A failing event-stream TTL refresh does not undo a published event
A publish SHALL be reported as successful when the Valkey-backed live event bus has
appended the event to a job's stream and only the subsequent time-to-live refresh of
that stream fails. That failure SHALL be logged as one warning without a stack trace.

The event is in the stream at that point and every subscriber will receive it, and the
next publish for the job refreshes the TTL again, so a missed refresh can at worst
expire the stream of a job that has stopped producing events. Failing the publish
instead discarded work that had already succeeded and aborted the model call that was
mid-response (DRA-42).

Appending the event SHALL continue to raise on failure. Losing the event itself is a
real failure, and the decision to tolerate it belongs to the layer that knows a durable
row was written.

#### Scenario: TTL refresh fails after the event is appended
- **WHEN** appending the event to the job's Valkey stream succeeds and refreshing that stream's TTL raises a connection error
- **THEN** the publish SHALL return the published event
- **AND** SHALL log one warning without exception info

#### Scenario: Appending the event still fails
- **WHEN** appending the event to the job's Valkey stream raises a connection error
- **THEN** the publish SHALL raise to its caller

### Requirement: Recoverable live-bus failures log one traceback per outage
Repeated failures of the same live-bus operation SHALL NOT emit one stack trace each.
The first failure of a streak SHALL be logged with exception info, later failures SHALL
be logged as counted warnings at a rate that grows sub-linearly with the streak length,
and the end of a streak SHALL be logged once with the number of failures it contained.

This extends the discipline established in DRA-35 to a call rate that change did not
face. The ingest loop it fixed is paced by a retry sleep, so one line per retry is
bounded; a live publish is paced by nothing and is issued once per streaming delta.
Emitting a line per failure there would replace a crash with a log flood, which was the
outcome DRA-35 set out to prevent.

#### Scenario: A long streak of failures is a handful of lines
- **WHEN** the same live-bus operation fails twenty consecutive times
- **THEN** exactly one log record SHALL carry exception info
- **AND** the number of warning records SHALL be substantially fewer than the number of failures

#### Scenario: Recovery is visible
- **WHEN** a live-bus operation succeeds after a streak of failures
- **THEN** one record SHALL report the recovery and the length of the streak

## MODIFIED Requirements

### Requirement: Crashed prompt runs reach a terminal status
The worker SHALL drive every claimed prompt job to a terminal status no matter which error is raised while executing it. This includes error types the worker does not explicitly classify — for example timeouts, `ExceptionGroup` wrappers raised by task groups, and programming errors — and errors raised before the first model call, such as while loading the job, reading its model configuration, or checking for cancellation.

Any such error SHALL be classified, persisted as a `failure` event, and applied through job failure handling so the job ends as `"failed"` (or is re-queued when the classified failure is retryable and attempts remain). A prompt job SHALL NOT be left in the non-terminal `"running"` status because of an unhandled error. `asyncio.CancelledError` SHALL remain uncaught so worker shutdown continues to cancel in-flight jobs.

When the prompt run's own failure handling raises, the worker SHALL still mark the job `"failed"` with `error_code = "worker_crash"`.

A failure to announce a job's fate on the live event bus SHALL NOT be one of the errors that reaches that fallback. The prompt run's failure handling records the durable `failure` event, publishes it, and marks the job failed; because publishing is best-effort, a transport error there SHALL leave that sequence intact, so the job SHALL end with the `error_code` its real failure was classified as and SHALL carry exactly one `failure` event. Before DRA-42 a failed publish skipped `mark_job_failed` and escaped into the crash fallback, which did still reach `"failed"` but recorded the cause as `worker_crash` and left the job's event list carrying `failure` twice — a diagnosis lost to an unrelated transport error.

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

#### Scenario: Announcing a failure fails
- **WHEN** the live publish of a job's `failure` event raises a connection error
- **THEN** the job SHALL end with status `"failed"` carrying the `error_code` of the failure that actually occurred
- **AND** SHALL have exactly one `failure` job event

#### Scenario: The prompt of a crashed run survives into the next run
- **WHEN** a prompt job crashes and a later job runs in the same session with `multi_turn_memory` enabled
- **THEN** the crashed job's prompt SHALL appear as a `role: user` message in the replayed context
- **AND** SHALL be followed by the synthetic assistant note for failed jobs
