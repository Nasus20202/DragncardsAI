# Infrastructure

## MODIFIED Requirements

### Requirement: Git submodules for external source
The repository SHALL track upstream external projects as git submodules under `external/` so their source is pinned to a specific commit and available locally for reading and building.

The second game platform SHALL be tracked the same way: `external/marvel-lcg` SHALL be a git submodule of `https://github.com/z00lus/marvel-lcg.git` — the maintained "Ronin Edition" fork, which is the only variant with a working Linux and Docker path — pinned to a specific commit rather than tracking a branch. The project is sunset upstream and publishes no tags, so a commit pin is the only reproducible reference available.

A fresh checkout or a newly created git worktree SHALL run `git submodule update --init --recursive` before building or testing. `git worktree add` leaves `external/` empty, so in a worktree this is not optional housekeeping: without it the game-service tests and every platform image build fail on missing source.

#### Scenario: Submodules initialised on clone
- **WHEN** a developer clones the repo and runs `git submodule update --init --recursive`
- **THEN** `external/dragncards/` SHALL contain the `seastan/dragncards` source at the pinned commit, `external/dragncards-mc-plugin/` SHALL contain the `hone/dragncards-mc-plugin` source at the pinned commit, and `external/marvel-lcg/` SHALL contain the `z00lus/marvel-lcg` source at the pinned commit

#### Scenario: Submodule commit is explicit
- **WHEN** the `.gitmodules` file is inspected
- **THEN** each submodule SHALL have a tracked commit SHA, ensuring builds are reproducible across machines and over time
- **AND** the `external/marvel-lcg` entry SHALL name the `z00lus/marvel-lcg` remote and SHALL NOT be configured to follow a branch

#### Scenario: A worktree without initialised submodules fails loudly
- **WHEN** a developer creates a git worktree and builds or tests without running `git submodule update --init --recursive`
- **THEN** the failure SHALL name the uninitialised submodule path rather than presenting as an unrelated build or import error

### Requirement: Docker Compose orchestration from repo root
The full stack SHALL be startable with `docker compose build && docker compose up -d` from the repository root without any additional arguments or path changes.

`docker compose up` with no arguments SHALL start exactly one game platform — the DragnCards platform, as it does today. It SHALL NOT start both platforms, because the platforms are alternatives, each carries its own database and content build, and a developer working on one has no reason to pay for the other.

#### Scenario: Root compose includes external services
- **WHEN** `docker-compose.yaml` at the repo root is parsed
- **THEN** it SHALL include `external/docker/docker-compose.yaml` via the `include:` directive, pulling in postgres, mc-plugin, backend, and frontend

#### Scenario: Root compose adds game-service
- **WHEN** `docker compose up` is run
- **THEN** the `game-service` service defined in the root `docker-compose.yaml` SHALL start alongside the included external services and depend on `backend`

#### Scenario: Root compose adds agent orchestration services
- **WHEN** `docker compose up` is run
- **THEN** the `agent-orchestrator` service SHALL start alongside `game-service`, depend on the dedicated orchestrator PostgreSQL service and Bifrost from `docker-compose.infra.yaml`, and use its dedicated PostgreSQL for orchestration persistence and durable job state

#### Scenario: Root compose adds local observability services
- **WHEN** `docker compose up` is run
- **THEN** the stack SHALL also start a local pinned `grafana/otel-lgtm` service for observability and wire the first-party services plus the Bifrost gateway to export OTLP telemetry to it

#### Scenario: A default start brings up one platform only
- **WHEN** `docker compose up` is run with no profile selected
- **THEN** the DragnCards platform services SHALL start exactly as they do today
- **AND** no marvel-lcg container SHALL be created

### Requirement: External service Docker configuration
Docker build configuration for external services (backend, frontend, mc-plugin, marvel-lcg) SHALL live under `external/docker/` alongside the submodules they build from.

An external project's own Docker or Compose files SHALL NOT be included into this repository's compose graph. They are written to run that project standalone: they declare their own container names, publish their own fixed host ports unconditionally, mount host paths relative to their own checkout, and join no shared network. Our compose service and Dockerfile for such a project SHALL be ours, derived from the upstream's but owned here.

#### Scenario: Backend built from submodule
- **WHEN** `docker compose build backend` is run
- **THEN** the backend Dockerfile at `external/docker/backend/Dockerfile` SHALL copy source from `external/dragncards/backend/` (the submodule) rather than cloning from the internet

#### Scenario: Frontend built from submodule
- **WHEN** `docker compose build frontend` is run
- **THEN** the frontend Dockerfile at `external/docker/frontend/Dockerfile` SHALL copy source from `external/dragncards/frontend/` (the submodule)

#### Scenario: MC plugin built from submodule
- **WHEN** `docker compose build mc-plugin` is run
- **THEN** the mc-plugin Dockerfile at `external/docker/mc-plugin/Dockerfile` SHALL copy the Rust CLI source from `external/dragncards-mc-plugin/` (the submodule) and build it with `cargo build --release`

#### Scenario: marvel-lcg built from submodule through our own Dockerfile
- **WHEN** the marvel-lcg image is built
- **THEN** the Dockerfile at `external/docker/marvel-lcg/Dockerfile` SHALL build the client and server from `external/marvel-lcg/` (the submodule)
- **AND** the fork's own `docker-compose.yml` SHALL NOT be included by any compose file in this repository

#### Scenario: All external build contexts use repo root
- **WHEN** any external service image is built
- **THEN** the Docker build context SHALL be the repository root so that both `external/` (submodules) and `external/docker/` (config files) are accessible to the Dockerfile

### Requirement: Infrastructure-only lifecycle helper
`scripts/docker-infrastructure.sh` SHALL start, stop, and restart every infrastructure service and no application service, deriving the service list from the compose files that define infrastructure instead of hardcoding names, so that a newly added infrastructure service is covered without editing the script.

Infrastructure is every service defined in `docker-compose.infra.yaml` or `external/docker/docker-compose.yaml`; the application services are the ones defined in `docker-compose.yaml` itself (`game-service`, `agent-orchestrator`, `history-service`, `eval-service`, `dashboard`). Services gated behind an optional compose profile are excluded, so neither the `smoke` model runtime nor a profile-gated game platform is ever started or stopped by the infrastructure helper.

`INFRA_COMPOSE_FILES` in that script SHALL be the single place edited when the set of infrastructure compose files changes, and the service list SHALL continue to be derived from those files with `docker compose config --services`. A service added to a file already listed there SHALL require no script edit at all.

#### Scenario: Stopping infrastructure leaves no infrastructure running
- **WHEN** a developer runs `make infra-down` (`scripts/docker-infrastructure.sh stop`) against a running stack
- **THEN** every infrastructure container SHALL be stopped, including those that only ever started as an implicit `depends_on` dependency such as `dragncards-postgres`, `otel-lgtm`, and `lmstudio-proxy`
- **AND** only the application services SHALL be left running

#### Scenario: A new infrastructure service is covered without a script edit
- **WHEN** a service is added to `docker-compose.infra.yaml` or `external/docker/docker-compose.yaml`
- **THEN** `infra-up`, `infra-down`, and `infra-restart` SHALL cover it with no change to `scripts/docker-infrastructure.sh`

#### Scenario: A new infrastructure compose file is one edit
- **WHEN** infrastructure is split into an additional compose file
- **THEN** adding it to `INFRA_COMPOSE_FILES` SHALL be the only change required in `scripts/docker-infrastructure.sh`, and the service list SHALL still be derived with `docker compose config --services`

#### Scenario: A profile-gated platform is not started by the helper
- **WHEN** `scripts/docker-infrastructure.sh start` is run
- **THEN** the profile-gated marvel-lcg service SHALL NOT be started, so selecting a platform stays a deliberate act

#### Scenario: Actions target the combined compose project
- **WHEN** the helper runs any of its actions
- **THEN** it SHALL invoke `docker compose -f docker-compose.yaml` — the file that `include:`s the infrastructure compose files — so the containers acted on are the ones the full stack runs under, rather than a separate standalone project

#### Scenario: Infrastructure containers are stopped, not removed
- **WHEN** `scripts/docker-infrastructure.sh stop` completes
- **THEN** the infrastructure containers SHALL be stopped but still present, leaving `scripts/docker.sh down` and `down-clean` as the way to remove containers and volumes

## ADDED Requirements

### Requirement: marvel-lcg platform Docker configuration
The repository SHALL define its own compose service for the marvel-lcg platform, built from the `external/marvel-lcg` submodule through `external/docker/marvel-lcg/Dockerfile` with the repository root as build context, and declared in a compose file that the root `docker-compose.yaml` includes.

That service SHALL join the existing `dragncards-shared` network, whose `name:` is pinned identically in every compose file that declares it, so the platform is addressable by container hostname from `game-service` and needs no host port to be usable by the stack.

Its published host port SHALL be `${MARVEL_LCG_PORT:-4006}`, following the repository convention that every port the repository itself owns is an environment variable with a default rather than a hardcoded literal, so two checkouts can run side by side without colliding.

The container SHALL be given writable state paths for the platform's runtime files — its asset cache, replays, and SQLite game history — through the platform's documented CLI overrides, so that no state is written into the submodule working tree and a rebuild does not silently discard it.

The platform's card art SHALL NOT be vendored into the repository or into the image; it streams at runtime from the upstream card-image host. Every setting the service reads SHALL appear with a placeholder value in the documented environment example, and the README service table, architecture description, and platform-selection instructions SHALL be updated by the same change that adds the service.

#### Scenario: marvel-lcg image builds from the submodule
- **WHEN** the marvel-lcg image is built with the repository root as context
- **THEN** it SHALL be built from `external/marvel-lcg/` at the pinned commit and SHALL require no network clone of the platform's source

#### Scenario: The platform is reachable inside the stack by hostname
- **WHEN** the marvel-lcg service is running and `game-service` resolves it
- **THEN** it SHALL be reachable over the `dragncards-shared` network by container hostname, without depending on a published host port

#### Scenario: The published port is environment-configurable
- **WHEN** `MARVEL_LCG_PORT` is unset and when it is set to another value
- **THEN** the service SHALL publish `4006` in the first case and the configured port in the second, with no hardcoded host port literal in the compose file

#### Scenario: Platform state is written outside the submodule tree
- **WHEN** the marvel-lcg service runs a game and writes its asset cache, replays, and game history
- **THEN** those files SHALL be written to configured volumes rather than into the `external/marvel-lcg` working tree, leaving the submodule clean

### Requirement: Game platform selection by compose profile
The marvel-lcg compose service SHALL be gated behind an optional compose profile, so that starting a second game platform is an explicit choice. `docker compose up` with no profile SHALL start the DragnCards platform and no marvel-lcg container, keeping every existing local workflow byte-for-byte unchanged.

Starting the marvel-lcg platform SHALL require selecting its profile explicitly — `docker compose --profile <platform> up`, or the documented `Makefile` target that does so — and that target SHALL be added by the same change, alongside the README instructions for choosing a platform.

Because the DragnCards platform services remain profile-free for backward compatibility, running marvel-lcg without DragnCards SHALL be achieved by naming the services to start rather than by removing the DragnCards services from the default set.

#### Scenario: The default stack starts one platform
- **WHEN** `docker compose up` is run with no profile
- **THEN** the DragnCards backend, frontend, and plugin services SHALL start and no marvel-lcg container SHALL be created

#### Scenario: Selecting the profile starts the platform
- **WHEN** the documented profile is selected, through `docker compose --profile` or the documented `Makefile` target
- **THEN** the marvel-lcg service SHALL start, join `dragncards-shared`, and publish `${MARVEL_LCG_PORT:-4006}`

#### Scenario: Platform choice is documented where a developer looks
- **WHEN** a developer reads the README to start the stack
- **THEN** it SHALL state which platform a default start brings up and how to select the other

### Requirement: marvel-lcg is confined to the internal network and its debug endpoint is never exposed
The vendored marvel-lcg fork binds all interfaces (`0.0.0.0`) rather than loopback, and it serves an unauthenticated `GET /debug` whose command path reaches `exec()` behind an AST blocklist that is bypassable. The platform's developer has declined to fix it. Every mitigation below is therefore mandatory, not advisory, and each SHALL be verified by a test rather than by inspection.

A password SHALL be configured for the marvel-lcg service, supplied through a non-committed environment variable with only a placeholder in the committed example. The service SHALL NOT be started with the fork's shipped empty password, because the platform's authentication check passes every caller when no password is set.

In a default deployment the service SHALL NOT be reachable from outside the internal Docker network. The published host port exists for local development only and SHALL be documented as such; a deployment that is not a developer's own machine SHALL publish no host port for it at all.

No first-party surface SHALL forward a request to the platform's `/debug` path, and no first-party surface SHALL proxy the platform generally: the dashboard's proxy fronts first-party services only, and `game-service` SHALL address only the platform endpoints its driver needs. The platform's cheat-mode query parameters SHALL never be composed by any first-party code.

#### Scenario: The service refuses to run without a password
- **WHEN** the marvel-lcg service is started with no password configured
- **THEN** startup SHALL fail with a message naming the missing password setting, rather than starting an instance whose authentication check admits every caller

#### Scenario: No committed file contains the password
- **WHEN** the repository's committed compose files and environment examples are inspected
- **THEN** the marvel-lcg password SHALL appear only as a placeholder or an environment-variable reference, never as a real value

#### Scenario: A default deployment publishes no host port for the platform
- **WHEN** the documented non-development deployment configuration is used
- **THEN** the marvel-lcg container SHALL be reachable only from the `dragncards-shared` network and SHALL publish no host port

#### Scenario: The debug endpoint is not reachable through any first-party surface
- **WHEN** a request for the platform's `/debug` path is attempted through the dashboard proxy and through every `game-service` route
- **THEN** no first-party surface SHALL forward it, and the attempt SHALL be refused by the surface it was made against
