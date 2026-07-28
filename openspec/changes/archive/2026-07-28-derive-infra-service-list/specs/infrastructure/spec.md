## ADDED Requirements

### Requirement: Infrastructure-only lifecycle helper

`scripts/docker-infrastructure.sh` SHALL start, stop, and restart every infrastructure
service and no application service, deriving the service list from the compose files that
define infrastructure instead of hardcoding names, so that a newly added infrastructure
service is covered without editing the script.

Infrastructure is every service defined in `docker-compose.infra.yaml` or
`external/docker/docker-compose.yaml`; the application services are the ones defined in
`docker-compose.yaml` itself (`game-service`, `agent-orchestrator`, `history-service`,
`eval-service`, `dashboard`). Services gated behind an optional compose profile are
excluded, so the `smoke` model runtime is never started or stopped by the infrastructure
helper.

#### Scenario: Stopping infrastructure leaves no infrastructure running

- **WHEN** a developer runs `make infra-down` (`scripts/docker-infrastructure.sh stop`)
  against a running stack
- **THEN** every infrastructure container SHALL be stopped, including those that only ever
  started as an implicit `depends_on` dependency such as `dragncards-postgres`,
  `otel-lgtm`, and `lmstudio-proxy`
- **AND** only the application services SHALL be left running

#### Scenario: A new infrastructure service is covered without a script edit

- **WHEN** a service is added to `docker-compose.infra.yaml` or
  `external/docker/docker-compose.yaml`
- **THEN** `infra-up`, `infra-down`, and `infra-restart` SHALL cover it with no change to
  `scripts/docker-infrastructure.sh`

#### Scenario: Actions target the combined compose project

- **WHEN** the helper runs any of its actions
- **THEN** it SHALL invoke `docker compose -f docker-compose.yaml` — the file that
  `include:`s the infrastructure compose files — so the containers acted on are the ones
  the full stack runs under, rather than a separate standalone project

#### Scenario: Infrastructure containers are stopped, not removed

- **WHEN** `scripts/docker-infrastructure.sh stop` completes
- **THEN** the infrastructure containers SHALL be stopped but still present, leaving
  `scripts/docker.sh down` and `down-clean` as the way to remove containers and volumes
