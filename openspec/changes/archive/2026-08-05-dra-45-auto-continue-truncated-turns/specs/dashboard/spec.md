## ADDED Requirements

### Requirement: The transcript shows when the service resumed a turn

The Play transcript SHALL render an automatic continuation as its own visible entry
between the partial output and the output that continued it, whenever the
agent-orchestrator resumes a turn the provider truncated. Two model-output blocks with
nothing between them read as one answer the model chose to write in two parts,
which is not what happened and hides the fact that the service spent an extra
provider call.

The entry SHALL name the provider stop reason that caused the continuation and
which continuation it is out of the configured maximum, so a reader of a bug
report can tell a single nudge from a model that is being truncated repeatedly.

`turn_continued` SHALL be present in the dashboard's subscribed stream event list.
The browser subscribes per named event type with no unnamed fallback, so a type
absent from that list never arrives live and appears only after a reconnect
replays it from the durable log.

`turn_continued` SHALL be passed through the shared event aggregation unchanged.
The aggregator's fallback branch interprets an unrecognised type as a tool call,
which would render a continuation as a tool card that never completes.

`turn_continued` SHALL NOT be treated as terminal. A continued turn is still
running, and treating it as terminal would show the job as finished while it is
still producing output.

Every event type the Play transcript renders SHALL also be selectable in the
subagent output view, so a continuation inside a subagent's run is visible in the
same way it is in the parent's.

#### Scenario: A continuation is visible between the two segments
- **WHEN** a job's events contain a `model_output`, then a `turn_continued`, then a second `model_output`
- **THEN** the transcript SHALL render a visible entry between the two output blocks
- **AND** that entry SHALL name the provider stop reason and the continuation number

#### Scenario: A continuation arrives live
- **WHEN** the dashboard is streaming a running job
- **THEN** `turn_continued` SHALL be among the event types it subscribes to, so the entry appears without waiting for a reconnect

#### Scenario: A continuation is not rendered as a tool call
- **WHEN** the shared event aggregation receives a `turn_continued` event
- **THEN** it SHALL pass the event through unchanged
- **AND** SHALL NOT produce a pending tool-call entry from it

#### Scenario: A continued job is still shown as running
- **WHEN** a `turn_continued` event arrives for the streaming job
- **THEN** the dashboard SHALL keep showing the job as streaming
