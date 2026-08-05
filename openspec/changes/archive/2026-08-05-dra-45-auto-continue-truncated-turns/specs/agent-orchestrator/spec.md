## ADDED Requirements

### Requirement: The reason a model stopped is captured on every response shape

The gateway client SHALL carry the model's stop reason on every chat response it
returns, so that a caller can distinguish a model that finished its answer from
one the provider cut off. A caller SHALL NOT have to inspect the raw response
body to learn it, because that body has two different shapes — a list of
streamed chunks when streaming and the whole response document when not — and a
caller that has to know which is a caller that will eventually handle only one.

The stop reason SHALL be read from one choice in a fixed priority order: the
OpenAI-compatible `finish_reason` first, then OpenRouter's `native_finish_reason`
passthrough of the upstream provider's own value, then an Anthropic-shaped
`stop_reason` at either the choice or the message level. A normalised value
therefore always wins over a vendor spelling of the same thing.

When streaming, the stop reason SHALL be taken from the **last** chunk that
carries a non-null one, because providers differ over whether they send it on the
final chunk or earlier.

A response that carries no stop reason in any of those positions SHALL report
none, rather than a guess inferred from the response's content.

#### Scenario: A streamed response reports why it stopped
- **WHEN** the gateway streams a completion whose final chunk carries `finish_reason` of `"length"`
- **THEN** the returned response SHALL report a stop reason of `"length"`

#### Scenario: A non-streamed response reports why it stopped
- **WHEN** the gateway returns a completion whose choice carries `finish_reason` of `"stop"`
- **THEN** the returned response SHALL report a stop reason of `"stop"`

#### Scenario: A vendor spelling is not lost
- **WHEN** a choice carries no `finish_reason` but carries `native_finish_reason` or an Anthropic-shaped `stop_reason`
- **THEN** the returned response SHALL report that value

#### Scenario: A normalised reason wins over a vendor one
- **WHEN** a choice carries both `finish_reason` and `native_finish_reason`
- **THEN** the returned response SHALL report the `finish_reason` value

#### Scenario: No stop reason is reported as none
- **WHEN** a response carries no stop reason in any recognised position
- **THEN** the returned response SHALL report no stop reason, and SHALL NOT infer one from the content

### Requirement: A turn truncated at the provider's output cap is continued automatically

A response carrying no tool calls SHALL NOT on its own be treated as the end of a
turn. A response truncated at the provider's output-token cap has exactly that
shape — some partial content, or none at all when a reasoning model spent its
whole budget thinking, and no tool calls — and completing the job on it reports a
turn the provider cut off as a turn the model finished.

When a response carries no tool calls **and** a stop reason meaning the output cap
was reached, the worker SHALL continue the same turn rather than complete the job:
it SHALL append the partial assistant content to the in-flight messages and a
continuation instruction as a user message, and take another round of the existing
tool-round loop.

The partial assistant content SHALL be appended only when it is non-empty, because
a provider may reject an assistant message with empty content and a reasoning model
can legitimately return none.

The vocabulary of stop reasons that mean truncation SHALL be matched
case-insensitively across vendors and SHALL cover at least OpenAI's `length`,
Anthropic's `max_tokens`, Gemini and Vertex's `MAX_TOKENS` and `max_output_tokens`,
and `max_completion_tokens`. Every other value — `stop`, `end_turn`, `tool_calls`,
`content_filter`, an unrecognised value, the empty string, and no value at all —
SHALL NOT be treated as truncation, so a model that chose to end its turn is never
forced onward.

The worker SHALL NOT infer truncation from the shape of the output — empty content,
absent tool calls, or content that does not end in sentence punctuation. Those fire
on legitimate short answers and would force a model onward for reasons unrelated to
any provider limit.

A turn that was continued and then finished SHALL reach status `completed`, because
it did finish. Its result text SHALL be every segment the turn produced joined in
order, not only the final one.

The tool-round-limit interrupt SHALL be unaffected: exhausting the round budget
SHALL still end the job as `interrupted` with its own message.

#### Scenario: A truncated turn is resumed rather than reported as finished
- **WHEN** a response carries no tool calls and a stop reason of `"length"`
- **THEN** the worker SHALL continue the turn with the partial content and a continuation instruction in the messages
- **AND** SHALL NOT mark the job completed on that response

#### Scenario: A model that chose to stop is left alone
- **WHEN** a response carries no tool calls and a stop reason of `"stop"`, `"end_turn"`, an unrecognised value, or none at all
- **THEN** the worker SHALL complete the job on that response

#### Scenario: A continued turn returns the whole answer
- **WHEN** a turn is truncated once and the continuation finishes it
- **THEN** the job SHALL reach status `completed`
- **AND** its result text SHALL contain both the partial segment and the continued segment, in order

#### Scenario: An empty partial output is not sent back as an empty assistant message
- **WHEN** a truncated response carries no content at all
- **THEN** the worker SHALL append only the continuation instruction, and SHALL NOT append an assistant message with empty content

### Requirement: Automatic continuation is bounded and can be disabled

Automatic continuation calls a paid provider without being asked, so it SHALL be
bounded and SHALL be switchable off.

The worker SHALL support a per-turn maximum number of automatic continuations,
configurable through `AUTO_CONTINUE_MAX_CONTINUATIONS`, defaulting to 3, and
rejected at startup when configured below 1. When the maximum is reached, the turn
SHALL complete exactly as it does with the behaviour absent, leaving the manual
follow-up available.

The counter SHALL be per turn and SHALL reset on any round that produced tool
calls, so what it bounds is consecutive truncations — a model that will not stop
being truncated — rather than unrelated truncations spread across a long turn.

The worker SHALL support disabling the behaviour entirely through
`AUTO_CONTINUE_TRUNCATED_TURNS`, defaulting to enabled. When disabled, a truncated
turn SHALL complete exactly as it does today.

Continuations SHALL consume rounds of the existing tool-round budget, so a
misconfigured continuation cap can never make a turn outlive that budget.

A cancellation requested during a continuation chain SHALL be honoured at the next
round boundary, with the same latency as a cancellation requested during a tool
call.

#### Scenario: A model that truncates every time still terminates
- **WHEN** every response is truncated and carries no tool calls
- **THEN** the worker SHALL continue the turn at most the configured maximum number of times
- **AND** SHALL then complete the job

#### Scenario: The behaviour can be switched off
- **WHEN** automatic continuation is disabled and a truncated response carries no tool calls
- **THEN** the worker SHALL complete the job on that response
- **AND** SHALL NOT record a continuation event

#### Scenario: A cancel during a continuation chain is honoured
- **WHEN** a cancellation is requested while a turn is being continued
- **THEN** the job SHALL reach status `cancelled` at the next round boundary

#### Scenario: A continuation cap below one is rejected
- **WHEN** `AUTO_CONTINUE_MAX_CONTINUATIONS` is configured as 0 or negative
- **THEN** configuration SHALL be rejected with a validation error

### Requirement: An automatic continuation never sends an over-window request

A continuation SHALL NOT be made when the request it would send does not fit the
model's context window. Each continuation makes the request strictly longer, and a
request can already approach or exceed that window before any continuation happens.
Continuing into that produces a truncate-continue-truncate spiral in which every
extra call is both futile and paid for.

Before each continuation the worker SHALL estimate the request it is about to send —
the in-flight messages including the partial content and the continuation
instruction — and SHALL refuse the continuation when that estimate reaches the same
budget automatic compaction uses, the model's context window multiplied by the
compaction threshold. A refused continuation SHALL complete the turn normally and
SHALL be logged with the estimate and the budget.

The estimate SHALL be produced by the service's existing context estimation, not by
a second estimator, so "too big to continue" and "too big to send" cannot drift
apart.

The context window SHALL be resolved from the gateway's model metadata, falling
back to the configured default window when the gateway cannot say, and SHALL be
resolved only when a truncation actually occurs so the ordinary path pays nothing
for it.

Automatic compaction SHALL NOT be invoked to make room. Compaction rewrites
persisted history and cannot shrink a message list already assembled for the turn
in progress, and shrinking it would discard the partial output the continuation
depends on.

#### Scenario: A request at the context budget is not continued
- **WHEN** a truncated response arrives and the request that a continuation would send is estimated at or above the context budget
- **THEN** the worker SHALL complete the turn
- **AND** SHALL NOT record a continuation event

#### Scenario: An unknown context window falls back rather than refusing everything
- **WHEN** the gateway reports no context length for the model
- **THEN** the worker SHALL apply the configured default context window size

### Requirement: An automatic continuation is recorded as its own event

The user SHALL be able to see that the service resumed a turn rather than that the
model produced one unbroken answer. Each automatic continuation SHALL be recorded
as a durable `turn_continued` job event, persisted and published under the durable
row's id so a live copy collapses into it rather than rendering twice.

Its payload SHALL carry the reason for the continuation, the raw provider stop
reason that triggered it, the 1-based continuation number, and the configured
maximum.

`turn_continued` SHALL NOT be a terminal event type in the job event stream: a
continued turn has not ended, and closing the stream on it would strand every
client watching the rest of the turn.

The partial output SHALL remain in the transcript as its own `model_output` event,
so the transcript reads as partial output, continuation marker, continued output.

Any event type the worker emits SHALL be registered in the dashboard's stream event
list, because the browser subscribes per named event type and silently drops any
type absent from that list.

A `turn_continued` event SHALL be replayed into a later turn's message history as a
note that the service resumed the turn, so the model is not shown two adjacent
assistant segments with no account of why they are separate.

#### Scenario: The seam is durably recorded
- **WHEN** a truncated turn is continued
- **THEN** a `turn_continued` job event SHALL be persisted with the provider stop reason, the continuation number and the configured maximum
- **AND** SHALL be published under the durable row's id

#### Scenario: A continuation does not close the event stream
- **WHEN** a client is streaming a job's events and a `turn_continued` event is emitted
- **THEN** the stream SHALL remain open and SHALL continue delivering the rest of the turn

#### Scenario: The partial output survives
- **WHEN** a truncated turn is continued
- **THEN** the partial segment SHALL remain a `model_output` event preceding the `turn_continued` event
- **AND** the continued segment SHALL be a separate `model_output` event following it

#### Scenario: A later turn is told the service resumed the earlier one
- **WHEN** a session whose history contains a `turn_continued` event is replayed for a later turn
- **THEN** the replayed history SHALL state that the service continued the turn automatically
