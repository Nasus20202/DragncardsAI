# Infrastructure Spec

## Purpose

This spec describes the local development infrastructure for DragnCardsAI. All services run via Docker Compose from the repo root. External upstream projects (DragnCards backend/frontend, Marvel Champions plugin) are tracked as git submodules and built from local source; the internally-developed Game Service is built from `services/game-service/`.
## Requirements
### Requirement: Git submodules for external source
The repository SHALL track upstream external projects as git submodules under `external/` so their source is pinned to a specific commit and available locally for reading and building.

#### Scenario: Submodules initialised on clone
- **WHEN** a developer clones the repo and runs `git submodule update --init`
- **THEN** `external/dragncards/` SHALL contain the `seastan/dragncards` source at the pinned commit and `external/dragncards-mc-plugin/` SHALL contain the `hone/dragncards-mc-plugin` source at the pinned commit

#### Scenario: Submodule commit is explicit
- **WHEN** the `.gitmodules` file is inspected
- **THEN** each submodule SHALL have a tracked commit SHA, ensuring builds are reproducible across machines and over time

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

### Requirement: Local smoke-model runtime wiring
The repository SHALL provide a documented local runtime path for a small `llama.cpp` model used by smoke tests, including the environment configuration needed for the dashboard and agent-orchestrator to target that model.

The smoke-model runtime SHALL remain optional for developers who are not running the smoke workflow.

#### Scenario: Smoke runtime can be started locally
- **WHEN** a developer follows the documented smoke-test setup for the local model runtime
- **THEN** the `llama.cpp` server SHALL be startable with the configured model artifact and reachable at the documented local endpoint

#### Scenario: Smoke runtime can be started through compose profile helper
- **WHEN** a developer runs the documented smoke helper or `make smoke-up` or `make smoke-model`
- **THEN** Docker Compose SHALL start the `llama-cpp-smoke-model-cache` and `llama-cpp-smoke` services under the optional `smoke` profile using the documented environment defaults

#### Scenario: Normal local stack does not require the smoke runtime
- **WHEN** a developer starts the normal local stack without the smoke-test workflow
- **THEN** the dashboard, game-service, and agent-orchestrator SHALL remain runnable without requiring the `llama.cpp` smoke-model process

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

### Requirement: External service Docker configuration
Docker build configuration for external services (backend, frontend, mc-plugin) SHALL live under `external/docker/` alongside the submodules they build from.

#### Scenario: Backend built from submodule
- **WHEN** `docker compose build backend` is run
- **THEN** the backend Dockerfile at `external/docker/backend/Dockerfile` SHALL copy source from `external/dragncards/backend/` (the submodule) rather than cloning from the internet

#### Scenario: Frontend built from submodule
- **WHEN** `docker compose build frontend` is run
- **THEN** the frontend Dockerfile at `external/docker/frontend/Dockerfile` SHALL copy source from `external/dragncards/frontend/` (the submodule)

#### Scenario: MC plugin built from submodule
- **WHEN** `docker compose build mc-plugin` is run
- **THEN** the mc-plugin Dockerfile at `external/docker/mc-plugin/Dockerfile` SHALL copy the Rust CLI source from `external/dragncards-mc-plugin/` (the submodule) and build it with `cargo build --release`

#### Scenario: All external build contexts use repo root
- **WHEN** any external service image is built
- **THEN** the Docker build context SHALL be the repository root so that both `external/` (submodules) and `external/docker/` (config files) are accessible to the Dockerfile

### Requirement: Game Service Docker configuration
The Game Service Dockerfile SHALL live alongside its source under `services/game-service/docker/`.

#### Scenario: Game service built from local source
- **WHEN** `docker compose build game-service` is run
- **THEN** the Dockerfile at `services/game-service/docker/Dockerfile` SHALL copy source from `services/game-service/` using the repo root as build context

### Requirement: Agent Orchestrator Docker configuration
The Agent Orchestrator Dockerfile SHALL live alongside its source under `services/agent-orchestrator/docker/`.

#### Scenario: Agent orchestrator built from local source
- **WHEN** `docker compose build agent-orchestrator` is run
- **THEN** the Dockerfile at `services/agent-orchestrator/docker/Dockerfile` SHALL copy source from `services/agent-orchestrator/` using the repo root as build context

#### Scenario: Agent orchestrator image includes skills
- **WHEN** `docker compose build agent-orchestrator` is run
- **THEN** configured local skill roots using the shape `skills/<skill_name>` SHALL be copied into the image so runtime skill discovery can resolve bundled skills

### Requirement: Bifrost gateway configuration
The infrastructure compose configuration in `docker-compose.infra.yaml` SHALL define a Bifrost AI gateway service using image `maximhq/bifrost` and configured through non-committed runtime secrets and provider environment variables.

#### Scenario: Bifrost starts with supported providers
- **WHEN** `docker compose up` is run with the required provider environment available
- **THEN** the `bifrost` service SHALL start with provider entries for OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini

#### Scenario: Provider secrets remain external
- **WHEN** repository files are inspected
- **THEN** provider API keys and access tokens SHALL NOT be committed in compose files, default env files, tests, or source code

#### Scenario: LM Studio traffic routes through lmstudio-proxy
- **WHEN** Bifrost sends a request to the `lmstudio` provider
- **THEN** the request SHALL be forwarded to `lmstudio-proxy` inside the Docker network rather than using `host.docker.internal` directly

### Requirement: LM Studio proxy
The infrastructure compose configuration SHALL define an `lmstudio-proxy` service using `alpine/socat` that forwards TCP connections from within the Docker network to the LM Studio server running on the host machine.

#### Scenario: Proxy forwards to host LM Studio
- **WHEN** any Docker service connects to `lmstudio-proxy` on port 80
- **THEN** the connection SHALL be forwarded to the host machine on `LMSTUDIO_HOST_PORT` (default: 1234)

#### Scenario: No service uses host.docker.internal for LM Studio
- **WHEN** compose files and service environment variables are inspected
- **THEN** no service SHALL reference `host.docker.internal` for LM Studio connectivity; all local model traffic SHALL route through `lmstudio-proxy`

### Requirement: Orchestrator PostgreSQL configuration
The infrastructure compose configuration in `docker-compose.infra.yaml` SHALL define a dedicated PostgreSQL service for the agent-orchestrator that is not shared with DragnCards or other services.

#### Scenario: Dedicated orchestrator database starts
- **WHEN** `docker compose up` is run
- **THEN** the orchestrator PostgreSQL service SHALL start from `docker-compose.infra.yaml` and provide storage used only by the agent-orchestrator

#### Scenario: Orchestrator database is isolated
- **WHEN** compose configuration is inspected
- **THEN** the agent-orchestrator SHALL connect to the dedicated orchestrator PostgreSQL service rather than `dragncards-postgres` or any other shared database service

### Requirement: External compose is independently usable
The external compose file at `external/docker/docker-compose.yml` SHALL be runnable on its own to bring up the DragnCards stack without the Game Service.

#### Scenario: External compose standalone startup
- **WHEN** a developer runs `docker compose -f external/docker/docker-compose.yml up -d` from the repo root
- **THEN** postgres, mc-plugin, backend, and frontend SHALL start successfully without requiring game-service

### Requirement: Eval Service Docker configuration
The infrastructure compose configuration SHALL define an `eval-service` and its dedicated PostgreSQL database with secret-free defaults, isolated from the history-service and agent-orchestrator databases.

#### Scenario: Eval-service and its database start
- **WHEN** `docker compose up` is run
- **THEN** the `eval-service` and its dedicated PostgreSQL service SHALL start and provide storage used only by the eval-service

#### Scenario: Eval database is isolated
- **WHEN** compose configuration is inspected
- **THEN** the eval-service SHALL connect to its own dedicated PostgreSQL service rather than the history-service, agent-orchestrator, or any other shared database service

### Requirement: Dedicated Bifrost judge identity
The infrastructure Bifrost gateway configuration SHALL define a dedicated judge virtual key/provider entry for evaluation traffic, separate from the game-playing provider keys, configured through non-committed runtime secrets so the judge has its own budget and recognizable identity.

#### Scenario: Dedicated judge key present in Bifrost configuration
- **WHEN** the Bifrost gateway configuration is inspected
- **THEN** a dedicated judge virtual key/provider entry SHALL be present, distinct from the game-playing keys, and the eval-service SHALL route judge traffic under it

#### Scenario: Judge key secret remains external
- **WHEN** repository files are inspected
- **THEN** the judge identity's API key or access token SHALL NOT be committed in compose files, default env files, tests, or source code

### Requirement: Shared internal Python library

The repository SHALL provide a single internal Python package,
`dragncards-common` (import name `dragncards_common`), under `services/shared/`,
that houses cross-service infrastructure code (the SQL migration runner, the
RESP/Valkey client, the Bifrost gateway error types + mapping, and the lazy
`httpx.AsyncClient` base) so that this logic lives in exactly one place rather
than being copy-pasted between services. Backend Python services that need this
code SHALL depend on it via a uv path source and SHALL NOT keep a private copy of
the extracted logic. The package SHALL treat OpenTelemetry as an optional
(soft) import so that a consumer without OpenTelemetry does not acquire the
dependency.

#### Scenario: Consuming service resolves the shared package

- **WHEN** a consuming service (`agent-orchestrator`, `eval-service`, or
  `history-service`) runs `uv sync`
- **THEN** `dragncards-common` SHALL resolve from the `../shared` path source and
  `dragncards_common` SHALL be importable by that service

#### Scenario: Shared package is packaged into service images

- **WHEN** a consuming service's `docker/Dockerfile` is built from the repo-root
  build context
- **THEN** the Dockerfile SHALL `COPY services/shared` before `uv sync` so the
  path-source dependency resolves inside the image and `dragncards_common`
  imports succeed at runtime

#### Scenario: RESP error replies are surfaced

- **WHEN** the shared RESP client reads a reply beginning with the `-` (error)
  prefix
- **THEN** it SHALL raise a `RespError` carrying the error text rather than
  silently ignoring it

