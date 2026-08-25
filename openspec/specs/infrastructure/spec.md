# Infrastructure Spec

## Purpose

This spec describes the local development infrastructure for DragnCardsAI. All services run via Docker Compose from the repo root. External upstream projects (DragnCards backend/frontend, Marvel Champions plugin) are tracked as git submodules and built from local source; the internally-developed Game Service is built from `services/game-service/`.

## Requirements

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

### Requirement: A failed RESP command is attributed to the call that failed
The shared RESP client SHALL NOT await the connection's close waiter while unwinding
from a failed command.

asyncio stores a single exception instance on a transport's protocol and hands that
same object to both the `StreamReader` and the connection's close waiter. Awaiting the
close waiter during unwinding therefore raises the exception that is already
propagating. Even when that second raise is caught and discarded, raising it appends
the close-time frames to the exception object's traceback, and the original exception
then escapes carrying a traceback that ends at the cleanup line instead of the call
that failed. That misattribution is what made a dead connection read as a cosmetic
close error in DRA-35.

The client SHALL still close the writer on every exit path, so no socket is leaked;
only the *await* is skipped, and only when the command has already failed.

A command that received a complete reply SHALL still await the close waiter, and that
await SHALL remain guarded, because a reset can legitimately arrive after a valid reply
and must not fail a command whose result is already in hand.

#### Scenario: A mid-command reset blames the read
- **WHEN** the peer resets the connection before sending a reply
- **THEN** `execute` SHALL raise the connection error with a traceback naming the RESP read, and that traceback SHALL NOT contain the close-waiter frames

#### Scenario: A reset after a complete reply is not an error
- **WHEN** the peer sends a complete reply and then resets the connection abortively
- **THEN** `execute` SHALL return the parsed reply and SHALL NOT raise

#### Scenario: The writer is closed on every path
- **WHEN** a command fails for any reason
- **THEN** the client SHALL still call `close()` on the writer before propagating

### Requirement: Node dependency build scripts are approved in version control

The repository's Node projects SHALL declare in version control which
dependencies may execute install (build) scripts, and SHALL treat an
undeclared one as an install failure, so that installing on a machine that has
never seen this repository produces the same dependency tree as CI without any
interactive approval step.

`services/dashboard` and `services/smoketest` are independent pnpm projects:
there is no root `package.json` and no repository-wide pnpm workspace, and each
project is installed from its own directory. Each SHALL carry its declaration in
its own `pnpm-workspace.yaml`, which is the file pnpm 11 reads these settings
from. The declaration SHALL NOT be recorded as `pnpm.onlyBuiltDependencies` in a
`package.json`: that key belongs to pnpm 10 and is absent from pnpm 11, so it
would be inert configuration that resembles protection.

Approval is expressed by the `allowBuilds` map, in which a package name mapped
to `true` may run its install script and a name mapped to `false` may not. A
package that has an install script and appears in neither state is unreviewed.
Each project SHALL set `strictDepBuilds: true`, which makes an unreviewed build
script fail the install rather than emit a warning. This is pnpm 11's default,
and it SHALL be pinned in the project anyway, because pnpm also resolves the
setting from user- and global-level configuration: a machine that disables it
would otherwise install a native package without its binary and report success,
deferring the failure to a missing `.node` file at run time.

A `true` entry grants a third-party package the right to execute arbitrary code
during every install, on every contributor machine and on every CI runner, so
the map SHALL be treated as a supply-chain boundary rather than a convenience
list. A package whose install script produces no artifact — install analytics,
a funding banner — SHALL be recorded as `false` rather than `true`, since
denying it costs nothing and leaves the decision stated. The set of packages
that need an entry SHALL be determined from the project's own dependency tree,
by emptying `allowBuilds` and reading the packages pnpm then refuses to build,
rather than copied from another project or assumed from a package's reputation.

Every install path SHALL pick these settings up without further configuration.
That holds for the CI workflow, which runs `pnpm install --frozen-lockfile` in
each project directory, and for the dashboard's Docker build, whose `deps` and
`builder` stages copy `pnpm-workspace.yaml` alongside `package.json` and
`pnpm-lock.yaml`.

#### Scenario: A clone with no prior pnpm state installs cleanly

- **WHEN** `pnpm install --frozen-lockfile` runs in `services/dashboard` against
  an empty `node_modules` on a machine where `pnpm approve-builds` has never
  been run for this repository
- **THEN** the install SHALL exit 0, SHALL NOT report any ignored build script,
  SHALL NOT prompt for approval, and SHALL leave `node_modules/.modules.yaml`
  recording no ignored and no pending builds

#### Scenario: Allowed native addons are actually built

- **WHEN** that install completes
- **THEN** the native artifacts of the allowed packages SHALL be present in
  `node_modules`, including those of `sharp`, `unrs-resolver`, `tree-sitter`,
  `tree-sitter-json` and `@tree-sitter-grammars/tree-sitter-yaml`
- **AND** `pnpm build` in `services/dashboard` SHALL exit 0

#### Scenario: An unreviewed build script fails the install

- **WHEN** a dependency that declares an install script is present in the tree
  and is named in neither the `true` nor the `false` state of `allowBuilds`
- **THEN** `pnpm install` SHALL fail with a non-zero exit code and SHALL name
  the offending package, rather than warning and linking it unbuilt

#### Scenario: A denied build script does not run and does not fail the install

- **WHEN** a package mapped to `false` — such as `@scarf/scarf`, whose
  postinstall reports install analytics over the network, or `core-js-pure`,
  whose postinstall prints a funding banner — is installed
- **THEN** its install script SHALL NOT run, and the install SHALL still exit 0
  without reporting it as ignored

#### Scenario: The approval list does not outlive the dependency

- **WHEN** a package named in `allowBuilds` is no longer present in the
  project's `pnpm-lock.yaml`
- **THEN** its entry SHALL be removed, so that the map never carries a standing
  pre-approval for a package that could re-enter the tree unreviewed

#### Scenario: A project with no build scripts still pins the strict setting

- **WHEN** a project such as `services/smoketest` has no dependency that
  declares an install script
- **THEN** it SHALL omit `allowBuilds` entirely and SHALL still set
  `strictDepBuilds: true`, so that a dependency which later introduces one is
  reviewed rather than skipped

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
