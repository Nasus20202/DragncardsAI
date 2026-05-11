## MODIFIED Requirements

### Requirement: Docker Compose orchestration from repo root
The full stack SHALL be startable with `docker compose build && docker compose up -d` from the repository root without any additional arguments or path changes.

#### Scenario: Root compose includes external services
- **WHEN** `docker-compose.yml` at the repo root is parsed
- **THEN** it SHALL include `external/docker/docker-compose.yml` via the `include:` directive, pulling in postgres, mc-plugin, backend, and frontend

#### Scenario: Root compose adds game-service
- **WHEN** `docker compose up` is run
- **THEN** the `game-service` service defined in the root `docker-compose.yml` SHALL start alongside the included external services and depend on `backend`

#### Scenario: Root compose adds agent orchestration services
- **WHEN** `docker compose up` is run
- **THEN** the `agent-orchestrator` service SHALL start alongside `game-service`, depend on the dedicated orchestrator PostgreSQL service and Bifrost from `docker-compose.infra.yaml`, and use its dedicated PostgreSQL for orchestration persistence and durable job state

#### Scenario: Root compose adds local observability services
- **WHEN** `docker compose up` is run
- **THEN** the stack SHALL also start a local `grafana/otel-lgtm:0.27.1` service for observability and wire the first-party services plus the Bifrost gateway to export OTLP telemetry to it

### Requirement: Service runtime infrastructure wiring
The repository's Compose configuration SHALL provide consistent runtime telemetry wiring for `game-service`, `agent-orchestrator`, `dashboard`, and the repo-managed Bifrost gateway when they run in the local stack.

#### Scenario: Compose injects telemetry configuration
- **WHEN** the instrumented services start in Docker Compose
- **THEN** each service SHALL receive configuration for OpenTelemetry export, including the local OTLP endpoint and a service-specific identity or plugin service name as appropriate

#### Scenario: Bifrost plugin is configured for local OTLP traces and metrics
- **WHEN** the Bifrost gateway starts in Docker Compose
- **THEN** its `services/bifrost/config.json` plugin configuration SHALL target the local collector for both traces and metrics using the documented OTel plugin settings

#### Scenario: Local observability UI is reachable from the host
- **WHEN** the local stack is running
- **THEN** developers SHALL be able to reach the LGTM-hosted observability UI from the host machine through a documented port mapping
