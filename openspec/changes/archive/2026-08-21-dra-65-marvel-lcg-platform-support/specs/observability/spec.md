# Observability

## ADDED Requirements

### Requirement: The marvel-lcg driver's edges are instrumented in game-service
`game-service` SHALL emit application-level spans covering each edge of its marvel-lcg driver, because none of those edges is explained by generic library instrumentation: the platform's protocol is a long-lived WebSocket that pushes render frames, plus short HTTP reads and writes whose responses carry no outcome of their own.

The instrumented edges SHALL be: game creation; the render-frame socket lifecycle (connect, announce, disconnect, and unexpected close); the world read; the enumerated-option read; move submission; and the two failure modes this platform makes possible — a submission that exhausted the driver's retry cap, and a prompt detected as stuck.

A submission span SHALL carry the outcome the driver concluded, not the platform's response status. The platform answers every submission `200` with an empty body and silently drops input for a seat it is not asking, so a span reporting the HTTP status reports nothing about whether the move landed.

Span granularity SHALL match the workflow, not the platform's frame rate. Render frames arrive per engine step and are very frequent — 35 arrived during setup before the first prompt — so the driver SHALL NOT emit one span per frame. Frames SHALL be covered by the socket-lifecycle span and by the spans for the prompts and moves they led to.

`game-service`'s unit tests SHALL assert that each of these edges is instrumented and SHALL pin the permitted span attribute keys, in the same way the other services' telemetry tests do, so an edge added later without a span is caught rather than shipping silent.

#### Scenario: Bringing a game up emits a span per edge
- **WHEN** `game-service` creates a marvel-lcg game, connects the render-frame socket, announces the client, and reads the world and the enumerated options
- **THEN** it SHALL emit an application-level span for each of those edges

#### Scenario: A submission span reports the driver's own outcome
- **WHEN** `game-service` submits a chosen option and the platform answers `200` with an empty body
- **THEN** the submission span SHALL carry the outcome the driver concluded from the state that followed, and SHALL NOT report success merely because the status was `200`

#### Scenario: Exhausting the retry cap is visible
- **WHEN** the driver reaches its submission retry cap for a prompt, or concludes that a prompt is stuck because the same frame, asked seats, prompt text and option identifiers recurred after a submission
- **THEN** it SHALL emit a span carrying that terminal outcome, so the condition is diagnosable without reproducing it

#### Scenario: Render frames do not each get a span
- **WHEN** the platform pushes many render frames while a game sets up and no seat is being asked
- **THEN** `game-service` SHALL emit no span per frame, and the frames SHALL be covered by the socket-lifecycle span

#### Scenario: Driver instrumentation is asserted by a test
- **WHEN** `game-service`'s telemetry unit tests run
- **THEN** they SHALL assert that each marvel-lcg driver edge is instrumented and SHALL assert the permitted span attribute keys

## MODIFIED Requirements

### Requirement: Telemetry never carries request bodies, prompts, model output, recorded game state, or credentials
Telemetry leaves the emitting process and the collector is readable by anyone who can reach it, so a span attribute is an exfiltration path. Span attributes, metric attributes and log attributes SHALL be limited to identifiers, names, scopes, counts, sequence numbers, mode flags, durations and outcome values.

The platform a span pertains to SHALL be permitted as an attribute. It is a short, low-cardinality slug drawn from a closed set (`dragncards`, `marvel-lcg`), it is the dimension by which two platforms' latency and failure rates are compared, and it carries nothing about the game being played. Every first-party service that handles work for more than one platform SHALL set it on its workflow spans, and it SHALL be included in the permitted attribute keys those services' tests pin.

The system SHALL NOT attach a request or response body, an assembled LLM prompt, a model or judge response, a recorded or live game state, a snapshot document, a recorded event payload, a Valkey value, or any credential, token or key to telemetry. Error text that may embed such content — for example an LLM gateway error body echoing the request — SHALL be recorded through the service's sanitizing durable-storage path and represented on the span by an outcome value only.

The marvel-lcg driver's payloads fall squarely inside that prohibition and SHALL NOT reach a span attribute: the platform's world descriptor, which is a full game state including cards visible only to one seat; the platform's prompt text; the enumerated option list, its target identifiers, and the chosen option's targets and payments; the platform's notification text; and its password or derived session token. A span for a prompt or a move SHALL carry counts and identifiers — how many options were offered, which option identifier was chosen, which seat, which platform, what outcome — and nothing that reconstructs the board or the decision.

#### Scenario: A workflow span carries only permitted attribute keys
- **WHEN** a first-party service emits an application-level workflow span
- **THEN** the span's attributes SHALL be drawn only from the permitted categories, and the permitted key set SHALL be asserted by that service's tests rather than left to review

#### Scenario: The platform is an attribute and the state is not
- **WHEN** `game-service` emits a workflow span for a move on either platform
- **THEN** the span SHALL carry the platform slug, the seat, the chosen option or action identifier, and the outcome
- **AND** it SHALL carry no game state, prompt text, option list, or target identifiers

#### Scenario: A platform credential never reaches a span
- **WHEN** `game-service` authenticates against marvel-lcg, or a request fails because a required cookie was absent and the platform answered with an HTML page
- **THEN** the span SHALL record the outcome only, and SHALL carry neither the configured password, the derived session token, nor the returned page body

#### Scenario: A gateway error carrying a secret and a prompt echo does not reach a span
- **WHEN** `eval-service` fails to grade a target because the gateway returned an error whose message embeds an authorization header and an echo of the judge prompt
- **THEN** the span for that target SHALL record only that the grading failed, and the detail SHALL be persisted through the sanitizing repository path that redacts credentials and truncates the text

#### Scenario: Snapshot and state handling workflows do not export the state
- **WHEN** `history-service` captures a snapshot or restores a game, both of which handle a full recorded game state
- **THEN** the spans covering those workflows SHALL carry only the game identifier, sequence numbers and mode flags, and SHALL NOT carry the snapshot document or any replayed event payload
