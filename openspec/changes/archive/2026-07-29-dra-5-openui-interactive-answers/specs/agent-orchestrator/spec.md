## ADDED Requirements

### Requirement: The agent can ask the user a question with fixed choices
The orchestrator SHALL offer a built-in `ask_user` tool to top-level prompt jobs, taking a question and between one and eight labelled choices, and optionally permitting a free-text answer. Child jobs and compaction jobs SHALL NOT be offered the tool, because no user surface is attached to them; a child job that calls it anyway SHALL receive an error result rather than a question nobody can see.

The tool SHALL validate the model's arguments before recording anything: the question must be non-empty, the number of choices must be within the permitted bound, every choice must carry a non-empty label and a non-empty value, choice values must be unique so that an answer identifies exactly one choice, and the question, labels, values, and descriptions must be within their length limits. A violation SHALL return an error result naming the problem so the model can correct itself, and SHALL NOT record a question.

The choices recorded for a question SHALL be exactly those the model offered, and SHALL be the authority against which a later answer is checked.

#### Scenario: Ask a question with choices
- **WHEN** a top-level job calls `ask_user` with a question and two valid choices
- **THEN** the system SHALL record a pending question carrying that question text and those two choices
- **AND** the system SHALL record and publish a `user_question` event carrying the question, its identifier, and the offered choices

#### Scenario: The tool is not offered to a child job
- **WHEN** the effective tool list is built for a child job
- **THEN** `ask_user` SHALL NOT appear in it

#### Scenario: Reject a question with no choices
- **WHEN** a job calls `ask_user` with an empty choice list
- **THEN** the system SHALL return an error result describing the problem and SHALL NOT record a question

#### Scenario: Reject duplicate choice values
- **WHEN** a job calls `ask_user` with two choices sharing the same value
- **THEN** the system SHALL return an error result describing the problem and SHALL NOT record a question

### Requirement: A pending question and its answer are durably stored
A question the agent is waiting on SHALL be stored in the relational database, together with the choices offered and, once given, the answer. It SHALL NOT be held in process memory, because the run that asks and the request that answers are separate processes that may be separate replicas, and because a pending question SHALL survive both a browser reload and a stream reconnect.

A stored question SHALL be in exactly one of three states: awaiting an answer, answered, or closed without an answer. Both transitions out of the awaiting state SHALL be applied conditionally on the question still awaiting an answer, so that exactly one caller can ever make each transition.

A question SHALL be removed when the job or session that owns it is deleted.

#### Scenario: A pending question outlives the request that created it
- **WHEN** a question has been recorded and the asking run is still waiting
- **THEN** the question and its offered choices SHALL be readable from the database by a different process

#### Scenario: A question is removed with its session
- **WHEN** the session owning a job with a recorded question is deleted
- **THEN** the question SHALL be removed as well

### Requirement: An answer is validated against the choices that were offered
The orchestrator SHALL expose an endpoint that records the user's answer to a specific question of a specific job. The endpoint SHALL accept exactly one of a chosen value or a free-text answer, and SHALL reject a request carrying both or neither as a bad request.

A chosen value SHALL be checked against the choices read back from the stored question. A value that was not offered SHALL be rejected as a bad request, so that a client cannot answer with something the model never offered and cannot widen the set of answers the model asked for. A free-text answer SHALL be rejected as a bad request unless the stored question permits free text.

An answer to an unknown job or an unknown question SHALL be rejected as not found. A question of a different job SHALL NOT be answerable through that job.

On success the endpoint SHALL record the answer, transition the question to answered, and record and publish a `user_question_answered` event naming the question and the answer given.

#### Scenario: Answer by choosing an offered value
- **WHEN** a client submits a chosen value that appears in the stored question's choices
- **THEN** the system SHALL record the answer, mark the question answered, and publish a `user_question_answered` event

#### Scenario: Reject a value that was never offered
- **WHEN** a client submits a chosen value that does not appear in the stored question's choices
- **THEN** the system SHALL reject the request as a bad request and the question SHALL remain awaiting an answer

#### Scenario: Reject free text the question did not permit
- **WHEN** a client submits a free-text answer to a question that does not permit free text
- **THEN** the system SHALL reject the request as a bad request and the question SHALL remain awaiting an answer

#### Scenario: Reject an answer carrying both forms
- **WHEN** a client submits both a chosen value and a free-text answer
- **THEN** the system SHALL reject the request as a bad request

### Requirement: A question is answered at most once
A question that is no longer awaiting an answer SHALL NOT be answerable. A second answer to a question that has already been answered, or an answer to a question that has been closed, SHALL be rejected as a conflict, and SHALL NOT alter the recorded answer.

An answer SHALL also be rejected as a conflict when the job that asked has reached a terminal status, because nothing is waiting to read it. This is what prevents an answer being accepted for a question whose run died without closing it.

The model SHALL therefore observe exactly one answer to any question it asked.

#### Scenario: The second answer is refused
- **WHEN** a question has been answered and a second answer is submitted for it
- **THEN** the system SHALL reject the second request as a conflict and the recorded answer SHALL be unchanged

#### Scenario: A closed question is not answerable
- **WHEN** a question has been closed without an answer and an answer is then submitted for it
- **THEN** the system SHALL reject the request as a conflict

#### Scenario: A question of a finished job is not answerable
- **WHEN** the job that asked a still-pending question has reached a terminal status and an answer is submitted
- **THEN** the system SHALL reject the request as a conflict

### Requirement: A run waiting on a question always resumes
The `ask_user` tool SHALL block the calling run until the question is answered or the wait ends, and SHALL always return a result the model can act on. The run SHALL NOT be suspended: the wait happens inside the tool call, and the answer re-enters the model's context as an ordinary tool result in the same message history every other tool result uses. No separate channel SHALL be introduced for it.

While waiting, the run SHALL treat the stored question as the authority and re-read it at a bounded interval, so that an answer recorded by another replica is observed even when no live event reaches the waiting run.

The wait SHALL be bounded by an absolute timeout, configurable together with the polling interval. When the timeout expires the run SHALL close the question, record and publish a `user_question_closed` event giving the reason as a timeout, and return a result stating that nobody answered and that the model should proceed on its own judgement or report that it is blocked. That result SHALL NOT be an error result, so the model does not read it as a transient failure to retry.

When the job's cancellation has been requested while waiting, the run SHALL close the question, record and publish a `user_question_closed` event giving the reason as cancellation, and stop waiting.

Closing a question SHALL happen before the run stops waiting on it, so that an answer submitted afterwards is refused rather than recorded against a question nobody is reading.

#### Scenario: The answer reaches the model as a tool result
- **WHEN** a user answers a pending question by choosing an offered value
- **THEN** the waiting `ask_user` call SHALL return a result naming the chosen answer
- **AND** that result SHALL be appended to the run's message history as the tool result for that call

#### Scenario: Nobody answers
- **WHEN** the wait for an answer reaches its timeout
- **THEN** the system SHALL close the question with a timeout reason, publish a `user_question_closed` event, and return a non-error result telling the model that nobody answered

#### Scenario: A late answer to a timed-out question is refused
- **WHEN** an answer is submitted for a question that the wait already closed on timeout
- **THEN** the system SHALL reject it as a conflict

#### Scenario: The job is cancelled while waiting
- **WHEN** cancellation is requested for a job that is waiting on a question
- **THEN** the system SHALL close the question with a cancellation reason and the run SHALL stop waiting

### Requirement: Question activity appears on the job's event timeline
The events `user_question`, `user_question_answered`, and `user_question_closed` SHALL each be both persisted against the job and published on the live event bus, following the existing pairing used by every other job event. None of them SHALL be treated as a terminal event, so the event stream stays open while the user decides.

Each event SHALL carry the question identifier, so that a consumer can match an answer or a closure to the question it resolves. The answered event SHALL carry the answer given and whether it came from a choice or from free text; the closed event SHALL carry the reason it was closed.

Because these events are persisted, a consumer that replays a job's events SHALL be able to reconstruct every question's current state without any additional endpoint.

#### Scenario: The timeline reconstructs a question's state
- **WHEN** a consumer replays a job's persisted events from the beginning
- **THEN** it SHALL find the `user_question` event and, if the question was resolved, the matching `user_question_answered` or `user_question_closed` event carrying the same question identifier

#### Scenario: A question does not close the event stream
- **WHEN** a `user_question` event is published for a running job
- **THEN** the job's event stream SHALL remain open
