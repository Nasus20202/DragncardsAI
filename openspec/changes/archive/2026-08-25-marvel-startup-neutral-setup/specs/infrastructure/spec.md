## MODIFIED Requirements

### Requirement: Docker Compose orchestration from repo root

The full stack SHALL be startable with `docker compose build && docker compose up -d` from the
repository root without any additional platform profile or path change. Ordinary application and
infrastructure startup SHALL start the DragnCards services, the marvel-lcg engine, and the
marvel-lcg initialization service together. The two game engines remain alternative game backends
selected per session; starting both containers does not merge their game state.

The marvel-lcg service SHALL be healthy before game-service reports that the Marvel backend is
available, and `marvel-lcg-init` SHALL complete its one-time asset/runtime initialization through
the ordinary dependency graph. The engine SHALL remain an internal backend dependency rather than
becoming a dashboard-proxied first-party service.

#### Scenario: Ordinary startup includes the Marvel engine

- **WHEN** a developer runs `docker compose up -d` without a profile argument
- **THEN** the `marvel-lcg` container SHALL be created and started
- **AND** the `marvel-lcg-init` service SHALL run through the same startup graph
- **AND** game-service SHALL be able to create a marvel-lcg session without a second Compose command

#### Scenario: Root compose includes external services

- **WHEN** `docker-compose.yaml` at the repo root is parsed
- **THEN** it SHALL include `external/docker/docker-compose.yaml` via the `include:` directive,
  pulling in postgres, mc-plugin, backend, and frontend

#### Scenario: Root compose adds game-service

- **WHEN** `docker compose up` is run
- **THEN** the `game-service` service defined in the root `docker-compose.yaml` SHALL start
  alongside the included external services and depend on `backend`

#### Scenario: Root compose adds agent orchestration services

- **WHEN** `docker compose up` is run
- **THEN** the `agent-orchestrator` service SHALL start alongside `game-service`, depend on the
  dedicated orchestrator PostgreSQL service and Bifrost from `docker-compose.infra.yaml`, and use
  its dedicated PostgreSQL for orchestration persistence and durable job state

#### Scenario: Root compose adds local observability services

- **WHEN** `docker compose up` is run
- **THEN** the stack SHALL also start a local pinned `grafana/otel-lgtm` service for observability
  and wire the first-party services plus the Bifrost gateway to export OTLP telemetry to it

#### Scenario: No profile is required for Marvel readiness

- **WHEN** the ordinary stack readiness checks run
- **THEN** they SHALL wait for the Marvel engine and its initialization dependency using the
  configured health/base URL
- **AND** a missing profile selection SHALL not be reported as the reason for an otherwise healthy
  deployment to lack the backend

#### Scenario: A default start brings up one platform only

- **WHEN** a developer runs the default start with no profile selected
- **THEN** both backend containers SHALL be available, while each created session SHALL still be
  routed to exactly one selected backend
- **AND** neither engine SHALL receive the other backend's setup or move payload

#### Scenario: The backends remain separate

- **WHEN** a DragnCards session and a marvel-lcg session are created in the ordinary stack
- **THEN** each session SHALL be routed to its selected backend
- **AND** neither engine SHALL receive the other backend's setup or move payload

#### Scenario: The Marvel engine is not dashboard-proxied

- **WHEN** the dashboard service set and proxy routes are inspected
- **THEN** `marvel-lcg` SHALL not be included as a first-party dashboard service key
- **AND** no dashboard route SHALL forward to the engine's debug or arbitrary-command surface

### Requirement: Infrastructure-only lifecycle helper

`scripts/docker-infrastructure.sh` SHALL start, stop, and restart every infrastructure service
defined by its compose inputs, including `marvel-lcg` and `marvel-lcg-init`, without requiring a
profile argument. Its service list SHALL remain derived from the compose files rather than being a
second hardcoded list. Stopping infrastructure SHALL not delete the Marvel engine's persistent
volumes.

#### Scenario: Infrastructure startup includes Marvel

- **WHEN** a developer runs the ordinary infrastructure start helper
- **THEN** the helper SHALL include `marvel-lcg` and its initialization service in the derived
  service set
- **AND** the engine SHALL be ready for game-service before the helper reports success

#### Scenario: Stopping infrastructure leaves no infrastructure running

- **WHEN** a developer runs `make infra-down` (`scripts/docker-infrastructure.sh stop`) against a
  running stack
- **THEN** every infrastructure container SHALL be stopped, including DragnCards PostgreSQL,
  `otel-lgtm`, `lmstudio-proxy`, `marvel-lcg`, and its initializer
- **AND** only application services SHALL be left running

#### Scenario: A new infrastructure service is covered without a script edit

- **WHEN** a service is added to `docker-compose.infra.yaml` or `external/docker/docker-compose.yaml`
- **THEN** `infra-up`, `infra-down`, and `infra-restart` SHALL cover it with no change to the
  lifecycle script

#### Scenario: A new infrastructure compose file is one edit

- **WHEN** infrastructure is split into an additional compose file
- **THEN** adding it to `INFRA_COMPOSE_FILES` SHALL be the only lifecycle-script change required
- **AND** its service list SHALL still be derived with `docker compose config --services`

#### Scenario: A profile-gated platform is not started by the helper

- **WHEN** `scripts/docker-infrastructure.sh start` is run
- **THEN** the helper SHALL start the ordinary Marvel backend without requiring a profile, and no
  profile-gated platform SHALL remain hidden from the ordinary service set

#### Scenario: Actions target the combined compose project

- **WHEN** the helper runs any of its actions
- **THEN** it SHALL invoke `docker compose -f docker-compose.yaml` so the containers acted on are
  the ones the full stack runs under

#### Scenario: Infrastructure containers are stopped, not removed

- **WHEN** the helper's stop action completes
- **THEN** infrastructure containers SHALL be stopped but still present
- **AND** its action SHALL not remove the Marvel engine's volumes

#### Scenario: Infrastructure stop preserves engine state

- **WHEN** a developer stops infrastructure
- **THEN** the Marvel engine and initializer containers SHALL be stopped according to the helper's
  lifecycle policy
- **AND** the engine's assets, runtime, and replay volumes SHALL remain present for the next start

### Requirement: External service Docker configuration

Docker build configuration for the external services SHALL continue to live under
`external/docker/`. The repository-owned `marvel-lcg` service and initializer SHALL be runnable in
the ordinary Compose graph without importing the vendored project's own Compose profile. The
vendored engine source SHALL remain read-only.

#### Scenario: The repository owns the ordinary Marvel service definition

- **WHEN** the root Compose graph is rendered with no profiles selected
- **THEN** the Marvel service and initializer SHALL be present from the repository-owned compose
  definition
- **AND** the vendored project's standalone Compose file SHALL not be required

#### Scenario: Backend built from submodule

- **WHEN** `docker compose build backend` is run
- **THEN** the backend Dockerfile SHALL copy source from `external/dragncards/backend/` rather than
  cloning from the internet

#### Scenario: Frontend built from submodule

- **WHEN** `docker compose build frontend` is run
- **THEN** the frontend Dockerfile SHALL copy source from `external/dragncards/frontend/`

#### Scenario: MC plugin built from submodule

- **WHEN** `docker compose build mc-plugin` is run
- **THEN** the mc-plugin Dockerfile SHALL copy source from `external/dragncards-mc-plugin/` and
  build it with `cargo build --release`

#### Scenario: marvel-lcg built from submodule through our own Dockerfile

- **WHEN** the marvel-lcg image is built
- **THEN** the Dockerfile at `external/docker/marvel-lcg/Dockerfile` SHALL build from
  `external/marvel-lcg/`
- **AND** the fork's own `docker-compose.yml` SHALL not be included by this repository's compose
  graph

#### Scenario: All external build contexts use repo root

- **WHEN** any external service image is built
- **THEN** the Docker build context SHALL be the repository root so both `external/` and
  `external/docker/` are accessible to the Dockerfile
