## ADDED Requirements

### Requirement: A live event and the durable row it copies are one event to a client

The agent-orchestrator SHALL deliver an event that it both persists and publishes in
a form that lets a streaming client recognise the two copies as one event.

The job event stream has two sources for the same event: it replays persisted rows
and it forwards the live event bus. Because almost every event the orchestrator
publishes is also appended to the job's event list, most live events are a second,
earlier copy of a row the same stream will also yield from storage. That earliness
is the point of the bus and SHALL be preserved.

Where a
publisher has already persisted the event, the published copy SHALL carry the
identifier of that durable row, and the stream SHALL present the copy to the client
under that identifier rather than under an identifier belonging to the bus. A bus
identifier — a stream entry id, or a counter — identifies a delivery, not an event,
and SHALL NOT be what a client keys on when a durable identifier exists.

A publisher that has persisted nothing of its own SHALL publish without a durable
identifier, and such an event SHALL keep the bus identifier, because no replay will
ever repeat it. Two cases SHALL be treated this way: an event whose durable home is
a different job, and an in-progress streaming chunk, which is a growing prefix of an
unfinished row rather than a copy of a finished one and is reconciled by its own
snapshot identifier.

An event that the orchestrator both persists and publishes SHALL carry the same
payload in both copies, since the two collapse into one and a consumer SHALL NOT see
less after a reload than it saw live.

Where the durable row is appended by a component that has no access to the event bus,
the event SHALL NOT be published a second time from elsewhere. The stream's own replay
SHALL be relied on to deliver it.

Every SSE frame the stream emits SHALL carry an event identifier, whether it came from
replay or from the live bus.

#### Scenario: A live copy of a persisted event reuses its identifier

- **WHEN** the orchestrator appends an event to a job's event list and publishes the
  same event on the live bus
- **THEN** the stream SHALL deliver both copies to the client under the identifier of
  the persisted row
- **AND** a client that de-duplicates on that identifier SHALL be left with one event

#### Scenario: A published event with no persisted row keeps the bus identifier

- **WHEN** an event is published on the live bus without a corresponding row in the
  job's event list
- **THEN** the stream SHALL deliver it under the bus's own identifier
- **AND** SHALL NOT suppress it, because no replay will repeat it

#### Scenario: A question renders once

- **WHEN** a job asks the user a question while a client is streaming its events
- **THEN** the client SHALL receive one identifiable `user_question` event
- **AND** a transcript built from those events SHALL contain one question for it

#### Scenario: A stream in flight across a deploy is still read

- **WHEN** a subscriber reads a live event that was published before the durable
  identifier was carried
- **THEN** it SHALL treat the identifier as absent and deliver the event under the
  bus identifier, rather than failing to read it

## MODIFIED Requirements

### Requirement: Question activity appears on the job's event timeline
The events `user_question`, `user_question_answered`, and `user_question_closed` SHALL each be both persisted against the job and published on the live event bus, following the existing pairing used by every other job event. None of them SHALL be treated as a terminal event, so the event stream stays open while the user decides.

Because each of the three is both persisted and published, each published copy SHALL carry the identifier of the durable row it copies, so that a client receiving both copies recognises them as one event and renders the question, its answer, or its closure once. Publishing a question without that identifier SHALL be regarded as a defect: the two copies then differ only by an identifier the client keys on, and the question is rendered twice.

Each event SHALL carry the question identifier, so that a consumer can match an answer or a closure to the question it resolves. The answered event SHALL carry the answer given and whether it came from a choice or from free text; the closed event SHALL carry the reason it was closed.

Because these events are persisted, a consumer that replays a job's events SHALL be able to reconstruct every question's current state without any additional endpoint.

#### Scenario: The timeline reconstructs a question's state
- **WHEN** a consumer replays a job's persisted events from the beginning
- **THEN** it SHALL find the `user_question` event and, if the question was resolved, the matching `user_question_answered` or `user_question_closed` event carrying the same question identifier

#### Scenario: A question does not close the event stream
- **WHEN** a `user_question` event is published for a running job
- **THEN** the job's event stream SHALL remain open

#### Scenario: One asked question is one event to a streaming client
- **WHEN** a running job records a question and publishes it while a client is streaming
- **THEN** the persisted copy and the published copy SHALL reach that client under the same identifier
- **AND** the client SHALL be able to reduce them to a single question awaiting an answer
