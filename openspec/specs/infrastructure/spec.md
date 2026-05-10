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
The infrastructure compose configuration in `docker-compose.infra.yaml` SHALL define a Bifrost AI gateway service using image `maximhq/bifrost:v1.5.0` and configured through non-committed runtime secrets and provider environment variables.

#### Scenario: Bifrost starts with supported providers
- **WHEN** `docker compose up` is run with the required provider environment available
- **THEN** the `bifrost` service SHALL start with provider entries for OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini

#### Scenario: Provider secrets remain external
- **WHEN** repository files are inspected
- **THEN** provider API keys and access tokens SHALL NOT be committed in compose files, default env files, tests, or source code

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
