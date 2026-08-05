## MODIFIED Requirements

### Requirement: A failing event-stream TTL refresh does not undo a published event

A publish SHALL NOT be able to fail *after* the event has reached the job's stream. Appending the event and refreshing that stream's time-to-live SHALL be one command, so there is no point in a publish at which the append has happened and the refresh has not.

DRA-42 reached the same outcome by tolerance: the refresh was a second command, a
reset on it aborted a publish whose event every subscriber had already received,
and that abort killed the model call that was mid-response. The guard that
swallowed it is removed here rather than kept, because the single command it is
replaced by leaves nothing for it to catch. Tolerance of a window is strictly
worse than not having the window, and a guard over an unreachable branch is
misleading to the next reader.

Appending the event SHALL continue to raise on failure. Losing the event itself is
a real failure, and the decision to tolerate it belongs to the layer that knows a
durable row was written — the best-effort wrapper every consumer in the running
service is handed, which turns it into a `None` return and a counted log line.

#### Scenario: The stream's expiry cannot fail apart from the append
- **WHEN** the Valkey-backed live event bus publishes an event
- **THEN** the expiry refresh SHALL be carried inside the same single command as the append
- **AND** no separate expiry command SHALL be issued that could fail on its own

#### Scenario: Appending the event still fails
- **WHEN** the single publish command raises a connection error
- **THEN** the publish SHALL raise to its caller
- **AND** the best-effort wrapper SHALL absorb it, returning no event rather than failing the job

## ADDED Requirements

### Requirement: The live-event path's Valkey cost is proportional to work, not to tokens or to elapsed time

The agent-orchestrator live-event path SHALL keep its Valkey command count proportional to the work actually done, rather than to the number of tokens a model streamed or the number of seconds a job has been open.

The client this path uses opens a fresh TCP connection and emits one command span
for every command, so a Valkey command, a TCP connection and a span are one unit
of cost rather than three.

Three properties SHALL hold.

**Publishing one live event SHALL cost one Valkey round trip.** Appending the
event to the job's stream and re-arming that stream's expiry SHALL be performed
as a single command. The expiry SHALL be re-armed on every append, because a job
that publishes nothing for longer than the expiry loses its stream key and the
next append would recreate that key with no expiry at all and leak it. Splitting
the append and the expiry into separate commands SHALL be regarded as a defect:
a streamed model response publishes one live event per token, so it doubles the
cost of the busiest path in the service.

**A live-event subscriber SHALL read multiple stream entries per command.** A
read SHALL request a bounded batch and SHALL retain entries it has taken off the
stream but not yet handed to its caller, serving them without issuing a further
command. The subscriber's public contract SHALL remain one event per call, so no
caller changes. That retained batch SHALL belong to the single subscription that
fetched it — one SSE request or one subagent wait — SHALL be bounded by the batch
size, and SHALL be discarded when the subscription closes; it SHALL NOT be
process-lifetime state. The cursor a subscriber resumes from SHALL be the last
entry it handed to its caller, so a subsequent read never replays a buffered
batch.

**An idle event stream SHALL NOT poll at the worker's job-claim rate.** How long a
quiet stream waits on the live event bus before re-reading a job's status from the
database SHALL be its own configured value, and SHALL NOT be taken from the
setting that governs how quickly the worker claims a queued job. That value is a
fallback interval and not a delivery-latency budget: a published event ends the
wait immediately, so no event a client receives is delayed by lengthening it. What
it bounds is only the detection of a job that reached a terminal status while
publishing nothing.

#### Scenario: One live event is one Valkey command

- **WHEN** the agent-orchestrator publishes a live job event to the Valkey live
  event bus
- **THEN** it SHALL issue exactly one Valkey command, that command SHALL both
  append the event and re-arm the stream's expiry, the stream key SHALL be passed
  as a declared key rather than interpolated into a script body, and the returned
  event SHALL carry the entry identifier the append produced

#### Scenario: A burst of streamed events is drained in far fewer commands than events

- **WHEN** a subscriber consumes a burst of live events published for one job
- **THEN** the number of Valkey commands it issues SHALL be bounded by the number
  of batches rather than the number of events, and each event SHALL still be
  handed to the caller individually and in publication order

#### Scenario: A subscription's buffered entries do not outlive it

- **WHEN** a live-event subscription is closed
- **THEN** any stream entries it had fetched and not yet delivered SHALL be
  discarded, so no entry is retained beyond the request or wait that fetched it

#### Scenario: The idle stream interval is configured separately from the worker tick

- **WHEN** the agent-orchestrator constructs the job event stream
- **THEN** the interval an idle stream waits on the live event bus SHALL come from
  a dedicated setting with its own environment variable and its own
  positive-value validation, and SHALL NOT be the worker's job-claim poll interval

#### Scenario: A terminal event already delivered from the database closes the stream without waiting

- **WHEN** a job event stream has delivered a terminal event that it read from the
  database
- **THEN** it SHALL make its remaining persisted-event pass and close, without
  first waiting the idle fallback interval on the live event bus, so that
  lengthening that interval never makes closing a finished stream slower

### Requirement: An event a client waits on is published, not left to the stream's fallback poll

An event the agent-orchestrator persists SHALL also be published on the live event bus whenever a client's view of the job depends on receiving it promptly.

Because the SSE stream serves both the live bus and a periodic `list_events` read,
a durable row with no matching publish still reaches the client — but only on the
stream's next fallback pass. That interval is a cost control, not a delivery
mechanism, and SHALL NOT be relied on to deliver anything a user waits on. Two
consequences are normative.

**A terminal event SHALL be published.** Until a terminal event is *delivered* the
client's stream stays open, so an unpublished one leaves a user who has just
cancelled a job watching a stream that never closes. This binds every writer of a
terminal row, including the cancellation of a queued job no worker will ever run,
and including each active child job cancelled alongside its parent, since a child
may have its own reader.

**A tool call and its result SHALL be published.** A tool call is recorded before
the tool runs, which is exactly when the live bus falls quiet, so leaving these to
the fallback pass makes a slow tool indistinguishable from a stalled agent.

Every such publish SHALL carry the identifier of the durable row it copies, so the
live copy and the copy the fallback pass yields are one event to the client rather
than two. A repository method that appends such a row SHALL surface that
identifier to its caller, which is what holds the bus, and SHALL NOT be given the
bus itself.

An event no client waits on MAY be left to the fallback pass, and where that
choice is made it SHALL be recorded as deliberate rather than left to be
rediscovered.

#### Scenario: Cancelling a job reaches an open stream without waiting the fallback interval

- **WHEN** a job with an open event stream is cancelled, with the stream's idle
  fallback interval configured longer than a user would wait
- **THEN** the `cancellation` SHALL reach that stream at once rather than on its
  next fallback pass, and SHALL carry the identifier of the durable `cancellation`
  row so the client renders one cancellation and not two

#### Scenario: Requesting cancellation surfaces an identifier per affected job

- **WHEN** cancellation is requested for a job that has active child jobs
- **THEN** the repository SHALL report the durable `cancellation` row it appended
  for the job and for each affected child, so the caller can announce each on that
  job's own stream

#### Scenario: A tool call is visible before the tool has finished running

- **WHEN** the orchestrator records a tool call and then invokes a tool that takes
  longer than the stream's idle fallback interval to return
- **THEN** the `tool_call` SHALL already have reached an open stream, so the
  transcript shows the call in progress rather than nothing, and the matching
  `tool_result` SHALL reach it on the same terms
