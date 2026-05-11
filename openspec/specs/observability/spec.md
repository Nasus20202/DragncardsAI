# Observability Spec

## Purpose

This spec describes the repository's OpenTelemetry-based local observability requirements for first-party services and the repo-managed Bifrost gateway.

## Requirements

### Requirement: Application services and gateway emit OpenTelemetry telemetry
The system SHALL configure `game-service`, `agent-orchestrator`, `dashboard`, and the repo-managed Bifrost gateway to emit OpenTelemetry telemetry with stable service identity and export it through OTLP using environment-driven configuration.

#### Scenario: Service identity is attached to exported telemetry
- **WHEN** any instrumented application service or the Bifrost gateway starts with telemetry enabled
- **THEN** it SHALL export telemetry with a stable `service.name` resource identifying that service

#### Scenario: Telemetry can be disabled for local runs
- **WHEN** a service starts with `OTEL_SDK_DISABLED=true`
- **THEN** the service SHALL continue to run normally without attempting to initialize exporters

#### Scenario: Bifrost gateway emits plugin-based telemetry
- **WHEN** the Bifrost gateway starts with its `otel` plugin enabled in `services/bifrost/config.json`
- **THEN** it SHALL export gateway traces through the configured collector using the `genai_extension` trace format

### Requirement: HTTP and runtime edges are instrumented across first-party services
The system SHALL instrument the highest-value request and runtime boundaries in each first-party service so developers can inspect latency and failures across inter-service flows.

#### Scenario: Python HTTP servers emit request telemetry
- **WHEN** `game-service` or `agent-orchestrator` handles an HTTP request
- **THEN** the service SHALL emit trace and metric data for that request including route-level attribution and response outcome

#### Scenario: Python HTTP server auto-instrumentation exports core request metrics
- **WHEN** `game-service` or `agent-orchestrator` handles HTTP traffic with telemetry enabled
- **THEN** the observability stack SHALL receive the `http_server_duration_milliseconds`, `http_server_active_requests`, and `http_server_response_size_bytes` metric families for that service

#### Scenario: Dashboard server emits server-side request telemetry
- **WHEN** `dashboard` handles a server-side route or proxy request
- **THEN** it SHALL emit server-side telemetry for that request and any upstream call it performs to first-party backend services

### Requirement: High-value dependency interactions are instrumented
The system SHALL instrument dependency interactions that provide the most diagnostic value for local development, including PostgreSQL, Valkey, and outbound HTTP requests used by the first-party services.

#### Scenario: Agent orchestrator emits PostgreSQL telemetry
- **WHEN** `agent-orchestrator` executes database work through its configured PostgreSQL engine
- **THEN** it SHALL emit telemetry for those database interactions

#### Scenario: Agent orchestrator exports SQLAlchemy connection metrics
- **WHEN** `agent-orchestrator` runs with SQLAlchemy auto-instrumentation enabled
- **THEN** the observability stack SHALL receive the `db_client_connections_usage` metric family for its PostgreSQL client activity

#### Scenario: Services emit Valkey telemetry
- **WHEN** `game-service` or `agent-orchestrator` performs Valkey-backed coordination or live-event operations
- **THEN** the service SHALL emit telemetry for those Valkey interactions

#### Scenario: Services emit outbound HTTP telemetry
- **WHEN** a first-party service makes an outbound HTTP call to DragnCards, Bifrost, or another configured service
- **THEN** it SHALL emit telemetry for the outbound request including success or failure outcome

#### Scenario: Python outbound HTTP auto-instrumentation exports client latency metrics
- **WHEN** `game-service` or `agent-orchestrator` performs outbound HTTP requests through the instrumented client runtime
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

#### Scenario: Game service traces session and action workflows
- **WHEN** `game-service` creates, restores, or executes actions against a managed game session
- **THEN** it SHALL emit application-level spans covering those workflow boundaries

#### Scenario: Agent orchestrator traces worker job workflows
- **WHEN** `agent-orchestrator` claims, runs, or completes a background prompt job
- **THEN** it SHALL emit application-level spans covering the job lifecycle and key downstream calls

### Requirement: Telemetry configuration uses OpenTelemetry conventions
The system SHALL configure exporter endpoints and core telemetry behavior through standard OpenTelemetry environment variables so the same services can run in Docker Compose or direct local development with minimal changes.

#### Scenario: Compose-provided OTLP endpoint is used by default
- **WHEN** a first-party service runs in the repository's Docker Compose stack
- **THEN** it SHALL use the configured OTLP endpoint from environment to export telemetry to the local observability backend

#### Scenario: Direct local run can override exporter destination
- **WHEN** a developer starts a first-party service outside Docker Compose with a different `OTEL_EXPORTER_OTLP_ENDPOINT`
- **THEN** the service SHALL use that configured endpoint instead of a hard-coded destination
