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

### Requirement: Infrastructure-only lifecycle helper
`scripts/docker-infrastructure.sh` SHALL start, stop, and restart every infrastructure service and no application service, deriving the service list from the compose files that define infrastructure instead of hardcoding names, so that a newly added infrastructure service is covered without editing the script.

Infrastructure is every service defined in `docker-compose.infra.yaml` or `external/docker/docker-compose.yaml`; the application services are the ones defined in `docker-compose.yaml` itself (`game-service`, `agent-orchestrator`, `history-service`, `eval-service`, `dashboard`). Services gated behind an optional compose profile are excluded, so the `smoke` model runtime is never started or stopped by the infrastructure helper.

#### Scenario: Stopping infrastructure leaves no infrastructure running
- **WHEN** a developer runs `make infra-down` (`scripts/docker-infrastructure.sh stop`) against a running stack
- **THEN** every infrastructure container SHALL be stopped, including those that only ever started as an implicit `depends_on` dependency such as `dragncards-postgres`, `otel-lgtm`, and `lmstudio-proxy`
- **AND** only the application services SHALL be left running

#### Scenario: A new infrastructure service is covered without a script edit
- **WHEN** a service is added to `docker-compose.infra.yaml` or `external/docker/docker-compose.yaml`
- **THEN** `infra-up`, `infra-down`, and `infra-restart` SHALL cover it with no change to `scripts/docker-infrastructure.sh`

#### Scenario: Actions target the combined compose project
- **WHEN** the helper runs any of its actions
- **THEN** it SHALL invoke `docker compose -f docker-compose.yaml` — the file that `include:`s the infrastructure compose files — so the containers acted on are the ones the full stack runs under, rather than a separate standalone project

#### Scenario: Infrastructure containers are stopped, not removed
- **WHEN** `scripts/docker-infrastructure.sh stop` completes
- **THEN** the infrastructure containers SHALL be stopped but still present, leaving `scripts/docker.sh down` and `down-clean` as the way to remove containers and volumes

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

Bifrost's cross-provider model listing answers only once every configured provider has answered, so a provider that is configured but unreachable delays the listing for every caller. Any provider whose endpoint is local — reached over the Docker network rather than the public internet — SHALL use a fast-failing retry policy so that its absence cannot hold the model listing for seconds. Specifically, the `lmstudio` provider's `network_config` SHALL use `max_retries: 1` with `retry_backoff_initial: 200` and `retry_backoff_max: 1000`.

#### Scenario: Bifrost starts with supported providers
- **WHEN** `docker compose up` is run with the required provider environment available
- **THEN** the `bifrost` service SHALL start with provider entries for OpenRouter, Mistral, Claude, OpenAI, LM Studio, and Gemini

#### Scenario: Provider secrets remain external
- **WHEN** repository files are inspected
- **THEN** provider API keys and access tokens SHALL NOT be committed in compose files, default env files, tests, or source code

#### Scenario: LM Studio traffic routes through lmstudio-proxy
- **WHEN** Bifrost sends a request to the `lmstudio` provider
- **THEN** the request SHALL be forwarded to `lmstudio-proxy` inside the Docker network rather than using `host.docker.internal` directly

#### Scenario: Absent LM Studio does not stall the model listing
- **WHEN** LM Studio is not running on the host and a client requests Bifrost's model listing
- **THEN** the `lmstudio` provider SHALL exhaust its retries in well under a second so the listing is not delayed by retry backoff

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
The external compose file at `external/docker/docker-compose.yaml` SHALL be runnable on its own to bring up the DragnCards stack without the Game Service.

#### Scenario: External compose standalone startup
- **WHEN** a developer runs `docker compose -f external/docker/docker-compose.yaml up -d` from the repo root
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
The infrastructure Bifrost gateway configuration SHALL define a dedicated judge key entry for evaluation traffic under EVERY configured provider, separate from that provider's game-playing key, each sourced from its own non-committed runtime secret, so the judge has its own attributable credential and budget whichever provider it runs on.

Each judge entry SHALL be named identically across providers (`eval-judge`) and SHALL carry `"weight": 0.0`, which keeps it out of Bifrost's weighted key selection so game-playing traffic can never draw it. Because a `0.0`-weighted key is never auto-selected, the eval-service SHALL address it explicitly by name via the `x-bf-api-key` header, which resolves against the target provider's keys and overrides the weight. The `Authorization` bearer SHALL NOT be relied on to select a provider key: with `enforce_auth_on_inference` disabled, `allow_direct_keys` disabled, and no governance virtual keys defined, that header selects nothing.

Adding a judge identity for a further provider SHALL require only a config entry plus a new environment variable — no code change.

#### Scenario: Dedicated judge key present for every provider
- **WHEN** the Bifrost gateway configuration is inspected
- **THEN** every provider SHALL carry a judge key entry distinct from its game-playing key, at `"weight": 0.0`, sourced from a per-provider environment reference
- **AND** the eval-service SHALL route judge traffic under it by explicit name

#### Scenario: Judge traffic never falls back to a game-playing key
- **WHEN** the eval-service sends a judge request to a provider that has no judge key configured, or whose judge key secret is unset
- **THEN** the gateway SHALL reject the request with an explicit error naming the missing key and provider
- **AND** the request SHALL NOT be served using that provider's game-playing key

#### Scenario: Judging with a non-default provider
- **WHEN** an operator configures the judge model to route through a different provider, such as `openrouter`, and sets that provider's judge secret
- **THEN** judge traffic SHALL use that provider's own judge key rather than its game-playing key, with no code change

#### Scenario: Judge key secret remains external
- **WHEN** repository files are inspected
- **THEN** the judge identity's API key or access token SHALL NOT be committed in compose files, default env files, tests, or source code
- **AND** the per-provider judge variables SHALL be documented, with empty values, alongside the game-playing provider variables

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

### Requirement: Service agent guides are discoverable as `CLAUDE.md`

A directory carrying an `AGENTS.md` guide SHALL also expose that guide under the
`CLAUDE.md` name, as a relative symlink rather than a duplicated copy, so that
directory-scoped agent tooling discovers the guide closest to the files being
changed while `AGENTS.md` remains the single source of truth.

#### Scenario: Service directory exposes its guide under both names

- **WHEN** a service directory under `services/` contains an `AGENTS.md`
- **THEN** the same directory SHALL contain a `CLAUDE.md` symlink whose target is
  `AGENTS.md`
- **AND** the symlink SHALL be tracked by git as a symlink (mode `120000`) with a
  relative target, so it resolves in clones, git worktrees, and container copies

#### Scenario: Guide content is never duplicated

- **WHEN** a service's `AGENTS.md` is edited
- **THEN** reading `CLAUDE.md` in that directory SHALL yield the edited content
  with no second file to update

### Requirement: Browser CORS allowlist on every first-party HTTP service

`game-service`, `agent-orchestrator`, `history-service` and `eval-service` SHALL
each restrict browser cross-origin access to a configured allowlist of origins, and
SHALL NOT permit all origins with a wildcard.

The allowlist SHALL be configurable per service through an environment variable, so
that no deployment depends on an origin hardcoded for one machine, and SHALL default
to the local dashboard's browser origin. The variable SHALL be declared in the
service's `.env.example` and passed through in `docker-compose.yaml`.

A wildcard allowlist SHALL be regarded as a defect rather than a development
convenience. Docker Compose publishes each of these services on a host port, so a
wildcard allows any web page loaded in a developer's browser to reach the services'
destructive operations cross-origin — deleting a game's whole recorded history,
backfilling forged events into the ordered store, deleting an agent session, or
submitting a prompt that spends the owner's model budget. Those are the same
operations the MCP surface deliberately withholds from a model, so a wildcard makes
that exclusion decorative.

Restricting origins SHALL NOT be treated as authentication. It constrains browsers
only, for the methods that require a preflight; a non-browser client sends no
`Origin` header and is unaffected. Requiring a credential is a separate concern and
is not satisfied by this requirement.

#### Scenario: A foreign origin is refused a destructive preflight

- **WHEN** a browser on an origin outside a service's allowlist sends a CORS
  preflight requesting a destructive method — for example `DELETE` on
  history-service's `/games/{game_id}`, `POST` on its `/games/{game_id}/events` or
  `/import`, `DELETE` on game-service's `/games/{session_id}`, or `DELETE` on the
  orchestrator's `/sessions/{session_id}`
- **THEN** the service SHALL refuse the preflight and SHALL NOT return an
  `Access-Control-Allow-Origin` header, so that the browser never sends the request
  it was asking permission for

#### Scenario: A foreign origin cannot read a response

- **WHEN** a browser on an origin outside a service's allowlist makes a
  cross-origin request the browser sends without a preflight
- **THEN** the response SHALL carry no `Access-Control-Allow-Origin` header, so the
  calling page cannot read the response body

#### Scenario: The dashboard's origin is granted access explicitly

- **WHEN** a browser on an allowlisted origin sends a CORS preflight to any of the
  four services
- **THEN** the service SHALL grant it and SHALL return `Access-Control-Allow-Origin`
  set to that specific origin rather than to a wildcard

#### Scenario: A request carrying no Origin is unaffected

- **WHEN** a caller that sends no `Origin` header reaches any of the four services —
  the dashboard's own server-side proxy, another backend service, an MCP client, or
  a command-line tool
- **THEN** the request SHALL be served exactly as it would have been without any
  CORS configuration, and the response SHALL carry no CORS headers

#### Scenario: The allowlist is configured from the environment

- **WHEN** a service's CORS environment variable is set to a comma-separated list of
  origins
- **THEN** the service SHALL allow exactly those origins, ignoring surrounding
  whitespace and empty entries
- **AND** when the variable is unset, the service SHALL fall back to the local
  dashboard origin rather than to a wildcard

#### Scenario: The shipped default is pinned by a test

- **WHEN** the unit suite of each of the four services runs
- **THEN** it SHALL assert against the service's real application, over HTTP rather
  than by reading configuration, that a foreign origin is refused a destructive
  preflight, that an allowlisted origin is granted one, and that a request with no
  `Origin` still succeeds
- **AND** an edit that restores a wildcard allowlist, whether by widening the
  configured default or by hardcoding it in the application factory, SHALL fail that
  suite

