# Observability Spec

## Purpose

This spec describes the repository's OpenTelemetry-based local observability requirements for first-party services and the repo-managed Bifrost gateway.

## Requirements

### Requirement: Application services and gateway emit OpenTelemetry telemetry
The system SHALL configure `game-service`, `agent-orchestrator`, `history-service`, `eval-service`, `dashboard`, and the repo-managed Bifrost gateway to emit OpenTelemetry telemetry with stable service identity and export it through OTLP using environment-driven configuration.

Setting the OpenTelemetry environment variables for a service SHALL NOT be treated as having instrumented it. Telemetry is only wired when the service's own code installs the tracer, meter and logger providers at startup and instruments the edges it owns. A service whose environment names a collector but whose code never initializes the providers exports nothing while appearing correctly configured, and SHALL be regarded as uninstrumented.

#### Scenario: Service identity is attached to exported telemetry
- **WHEN** any instrumented application service or the Bifrost gateway starts with telemetry enabled
- **THEN** it SHALL export telemetry with a stable `service.name` resource identifying that service

#### Scenario: Every first-party service initializes providers in code at startup
- **WHEN** `game-service`, `agent-orchestrator`, `history-service`, `eval-service` or `dashboard` starts with telemetry enabled
- **THEN** its own startup path SHALL install the trace, metric and log providers before it begins serving, so that the global no-op providers are replaced rather than left in place

#### Scenario: Configuration alone does not satisfy the requirement
- **WHEN** a service is given `OTEL_SERVICE_NAME` and `OTEL_EXPORTER_OTLP_ENDPOINT` but its code contains no provider initialization and no instrumentation
- **THEN** the service SHALL be treated as failing this requirement, because the observability stack receives no telemetry from it

#### Scenario: Telemetry can be disabled for local runs
- **WHEN** a service starts with `OTEL_SDK_DISABLED=true`
- **THEN** the service SHALL continue to run normally without attempting to initialize exporters

#### Scenario: Bifrost gateway emits plugin-based telemetry
- **WHEN** the Bifrost gateway starts with its `otel` plugin enabled in `services/bifrost/config.json`
- **THEN** it SHALL export gateway traces through the configured collector using the `genai_extension` trace format

### Requirement: HTTP and runtime edges are instrumented across first-party services
The system SHALL instrument the highest-value request and runtime boundaries in each
first-party service so developers can inspect latency and failures across inter-service
flows.

The dashboard's set of trace-context propagation targets SHALL be derived from the single
declaration of the services the dashboard fronts, not written out as its own list of
service names. A hand-written list is what made history-service and eval-service invisible
in dashboard-initiated traces, and a test that hardcodes the same names cannot detect the
omission it is meant to prevent.

#### Scenario: Python HTTP servers emit request telemetry
- **WHEN** `game-service`, `agent-orchestrator`, `history-service` or `eval-service` handles an HTTP request
- **THEN** the service SHALL emit trace and metric data for that request including route-level attribution and response outcome

#### Scenario: Python HTTP server auto-instrumentation exports core request metrics
- **WHEN** `game-service`, `agent-orchestrator`, `history-service` or `eval-service` handles HTTP traffic with telemetry enabled
- **THEN** the observability stack SHALL receive the `http_server_duration_milliseconds`, `http_server_active_requests`, and `http_server_response_size_bytes` metric families for that service

#### Scenario: Dashboard server emits server-side request telemetry
- **WHEN** `dashboard` handles a server-side route or proxy request
- **THEN** it SHALL emit server-side telemetry for that request and any upstream call it performs to first-party backend services

#### Scenario: Dashboard propagates trace context to every first-party backend
- **WHEN** `dashboard` performs a server-side call to `game-service`, `agent-orchestrator`, `history-service` or `eval-service`, by Docker service name or by the host of its configured base URL
- **THEN** it SHALL propagate trace context on that call, so the backend's spans join the dashboard's trace as children instead of starting a separate trace
- **AND** the set of propagation targets SHALL be derived from the declared set of services the dashboard fronts, so a service added to that declaration is covered without a second list to update
- **AND** the set of propagation targets SHALL be asserted by a test driven by that same declaration, so adding a backend without covering it is caught rather than silently producing disconnected traces

#### Scenario: Propagation follows the configured upstream, not a fixed hostname
- **WHEN** a first-party backend's base URL is configured to a host other than the local default
- **THEN** the dashboard SHALL propagate trace context to that configured host as well as to the service's Docker service name

### Requirement: High-value dependency interactions are instrumented
The system SHALL instrument dependency interactions that provide the most diagnostic value for local development, including PostgreSQL, Valkey, and outbound HTTP requests used by the first-party services.

#### Scenario: Services with a database emit PostgreSQL telemetry
- **WHEN** `agent-orchestrator`, `history-service` or `eval-service` executes database work through its configured PostgreSQL engine
- **THEN** it SHALL emit telemetry for those database interactions

#### Scenario: Services with a database export SQLAlchemy connection metrics
- **WHEN** `agent-orchestrator`, `history-service` or `eval-service` runs with SQLAlchemy auto-instrumentation enabled
- **THEN** the observability stack SHALL receive the `db_client_connections_usage` metric family for its PostgreSQL client activity

#### Scenario: Services emit Valkey telemetry
- **WHEN** `game-service`, `agent-orchestrator` or `history-service` performs Valkey-backed coordination, live-event or stream-ingestion operations
- **THEN** the service SHALL emit telemetry for those Valkey interactions

#### Scenario: A shared Valkey client is given a tracer by every service that uses it
- **WHEN** a service constructs the shared RESP/Valkey client, which emits a command span only when it is supplied a tracer
- **THEN** that service SHALL supply its tracer, so that re-using the shared client never silently produces a service with no Valkey telemetry

#### Scenario: Services emit outbound HTTP telemetry
- **WHEN** a first-party service makes an outbound HTTP call to DragnCards, Bifrost, or another configured service
- **THEN** it SHALL emit telemetry for the outbound request including success or failure outcome

#### Scenario: Python outbound HTTP auto-instrumentation exports client latency metrics
- **WHEN** `game-service`, `agent-orchestrator`, `history-service` or `eval-service` performs outbound HTTP requests through the instrumented client runtime
- **THEN** the observability stack SHALL receive the `http_client_duration_milliseconds` metric family for those requests

### Requirement: Bifrost exports gateway metrics through OpenTelemetry
The system SHALL configure the Bifrost `otel` plugin to push gateway metrics to the local OTLP collector so local observability includes LLM gateway health and usage metrics.

#### Scenario: Bifrost metrics push is enabled
- **WHEN** the Bifrost gateway starts with the `otel` plugin configured for metrics export
- **THEN** it SHALL push OTLP metrics to the configured metrics endpoint at the configured interval

#### Scenario: Bifrost telemetry includes model request traces
- **WHEN** `agent-orchestrator` sends LLM requests through Bifrost
- **THEN** the observability stack SHALL receive Bifrost-generated GenAI traces for those gateway requests

### Requirement: Repo-specific workflows include manual telemetry spans
The system SHALL add manual spans around repo-specific workflows that are not fully explained by generic library instrumentation.

Manual span granularity SHALL match the workflow rather than the underlying event rate. A continuously polling loop SHALL be traced per batch of work rather than per polled iteration, so that an idle service does not flood the collector with empty spans.

#### Scenario: Game service traces session and action workflows
- **WHEN** `game-service` creates, restores, or executes actions against a managed game session
- **THEN** it SHALL emit application-level spans covering those workflow boundaries

#### Scenario: Agent orchestrator traces worker job workflows
- **WHEN** `agent-orchestrator` claims, runs, or completes a background prompt job
- **THEN** it SHALL emit application-level spans covering the job lifecycle and key downstream calls

#### Scenario: History service traces ingestion, snapshotting and restore
- **WHEN** `history-service` ingests a batch of recorded events, captures a snapshot, or restores a game to a past moment
- **THEN** it SHALL emit application-level spans covering each of those workflow boundaries, with the ingestion span covering a batch rather than an individual event

#### Scenario: Eval service traces the judge lifecycle per graded target
- **WHEN** `eval-service` grades an evaluation target
- **THEN** it SHALL emit one application-level span for that target carrying the target and request identifiers, the evaluation scope, and the terminal outcome of the grading attempt

### Requirement: Telemetry configuration uses OpenTelemetry conventions
The system SHALL configure exporter endpoints and core telemetry behavior through standard OpenTelemetry environment variables so the same services can run in Docker Compose or direct local development with minimal changes.

#### Scenario: Compose-provided OTLP endpoint is used by default
- **WHEN** a first-party service runs in the repository's Docker Compose stack
- **THEN** it SHALL use the configured OTLP endpoint from environment to export telemetry to the local observability backend

#### Scenario: Every app service waits for the collector to be healthy
- **WHEN** the Docker Compose stack starts an application service that exports telemetry
- **THEN** that service SHALL declare a dependency on the local observability service being healthy, so no app service starts before the collector can receive from it

#### Scenario: Direct local run can override exporter destination
- **WHEN** a developer starts a first-party service outside Docker Compose with a different `OTEL_EXPORTER_OTLP_ENDPOINT`
- **THEN** the service SHALL use that configured endpoint instead of a hard-coded destination

#### Scenario: Each service documents its telemetry variables
- **WHEN** a developer reads a first-party service's `.env.example`
- **THEN** it SHALL document the OpenTelemetry variables that service honours, using placeholder values only and no credential of any kind

### Requirement: One shared telemetry bootstrap for the Python services
The repository SHALL provide a single OpenTelemetry bootstrap implementation in the shared internal library `dragncards-common`, covering provider construction, OTLP exporter configuration, the `service.name` resource, the disabled-SDK no-op, trace-correlated log records, and the HTTP-server, outbound-HTTP and SQLAlchemy instrumentation helpers.

A Python service SHALL wire telemetry by binding its own service name to that shared bootstrap rather than by carrying its own copy of the setup code. Duplicated per-service bootstraps are what allowed two services to be added with none at all, so a new copy SHALL NOT be introduced.

`game-service` is a recorded exception: it is the only Python service that does not depend on `dragncards-common`, and its container image installs from its own lockfile with a frozen sync, so adopting the shared library requires a dependency and image change. It retains an equivalent local copy, and that exception SHALL be stated in the repository documentation so it is not mistaken for an oversight and does not license a third copy.

#### Scenario: A newly added Python service reuses the shared bootstrap
- **WHEN** a Python service is added to the repository and needs telemetry
- **THEN** it SHALL depend on `dragncards-common` and bind its own service name to the shared bootstrap, and SHALL NOT reimplement provider, exporter or instrumentation setup

#### Scenario: The shared library does not force a web or ORM dependency
- **WHEN** a consumer imports the shared telemetry module without FastAPI or SQLAlchemy instrumentation in use
- **THEN** the import SHALL succeed, because the framework-specific instrumentors are loaded only at the point they are applied

#### Scenario: The documented exception is visible
- **WHEN** a developer reads the repository's agent instructions or README about telemetry
- **THEN** they SHALL find `game-service`'s local copy named as a deliberate exception together with its reason

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

### Requirement: Span volume on a polling loop is reduced by issuing fewer commands, not by hiding spans

The requirement that a continuously polling loop be traced per batch of work rather than per polled iteration SHALL govern per-command dependency spans as well as application-level workflow spans.

A loop whose exported span count is dominated by idle iterations SHALL be regarded
as reporting a real defect in the loop, not as a telemetry defect, whenever the
instrumentation emits one span per underlying operation and therefore reports the
operation count faithfully.

Where a service's client emits one span per command and opens one connection per
command, a command, a connection and a span SHALL be treated as one quantity. The
remedy for too many such spans SHALL be to issue fewer commands — by batching, by
combining commands into a single round trip, or by lengthening a poll interval
that has no latency justification. Suppressing the tracer for a chatty path,
filtering the command span in the collector, or lowering the trace sample rate
SHALL NOT be used as the remedy while the underlying command count remains
disproportionate to the work performed, because each of those removes the only
signal that would reveal the cost while leaving the commands and the connections
in place.

Sampling and collector-side filtering remain legitimate once a path's command
count is proportionate to its work and the remaining span volume is a genuine
export-cost problem. That distinction SHALL be established by measurement — the
command count for a representative operation, compared against the span count for
the same operation — rather than asserted.

#### Scenario: A trace dominated by dependency spans from an idle loop is diagnosed as a loop defect

- **WHEN** a first-party service's trace is dominated by per-command dependency
  spans emitted by a loop that was idle
- **THEN** the command count for that loop SHALL be measured and compared against
  its span count, and where they match the loop SHALL be changed to issue fewer
  commands rather than to emit fewer spans

#### Scenario: A per-command span is not suppressed to reduce a trace's size

- **WHEN** a path emits one command span per Valkey command and its span volume is
  judged excessive
- **THEN** the tracer SHALL remain wired into that path, and the reduction SHALL
  come from the number of commands issued, so that the telemetry continues to
  report the service's real dependency load

#### Scenario: An interval with no latency justification is not set from an unrelated one

- **WHEN** a loop's poll or block interval controls only a fallback path, and a
  published event or an equivalent signal already ends the wait immediately
- **THEN** that interval SHALL be configured on its own terms and SHALL NOT be
  taken from a setting that governs an unrelated latency, so that its cost per
  second is a deliberate choice

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
