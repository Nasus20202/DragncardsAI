## MODIFIED Requirements

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
The system SHALL instrument the highest-value request and runtime boundaries in each first-party service so developers can inspect latency and failures across inter-service flows.

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
- **WHEN** `dashboard` performs a server-side call to `game-service`, `agent-orchestrator`, `history-service` or `eval-service`, by Docker service name or by the host port a direct local run uses
- **THEN** it SHALL propagate trace context on that call, so the backend's spans join the dashboard's trace as children instead of starting a separate trace
- **AND** the set of propagation targets SHALL be asserted by a test, so adding a backend without adding it to that set is caught rather than silently producing disconnected traces

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

## ADDED Requirements

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

The system SHALL NOT attach a request or response body, an assembled LLM prompt, a model or judge response, a recorded or live game state, a snapshot document, a recorded event payload, a Valkey value, or any credential, token or key to telemetry. Error text that may embed such content — for example an LLM gateway error body echoing the request — SHALL be recorded through the service's sanitizing durable-storage path and represented on the span by an outcome value only.

#### Scenario: A workflow span carries only permitted attribute keys
- **WHEN** a first-party service emits an application-level workflow span
- **THEN** the span's attributes SHALL be drawn only from the permitted categories, and the permitted key set SHALL be asserted by that service's tests rather than left to review

#### Scenario: A gateway error carrying a secret and a prompt echo does not reach a span
- **WHEN** `eval-service` fails to grade a target because the gateway returned an error whose message embeds an authorization header and an echo of the judge prompt
- **THEN** the span for that target SHALL record only that the grading failed, and the detail SHALL be persisted through the sanitizing repository path that redacts credentials and truncates the text

#### Scenario: Snapshot and state handling workflows do not export the state
- **WHEN** `history-service` captures a snapshot or restores a game, both of which handle a full recorded game state
- **THEN** the spans covering those workflows SHALL carry only the game identifier, sequence numbers and mode flags, and SHALL NOT carry the snapshot document or any replayed event payload
