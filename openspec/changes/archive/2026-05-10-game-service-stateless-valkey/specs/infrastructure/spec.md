## MODIFIED Requirements

### Requirement: Docker Compose orchestration from repo root
The full stack SHALL be startable with `docker compose build && docker compose up -d` from the repository root without any additional arguments or path changes.

#### Scenario: Root compose includes external services
- **WHEN** `docker-compose.yaml` at the repo root is parsed
- **THEN** it SHALL include `external/docker/docker-compose.yaml` via the `include:` directive, pulling in postgres, mc-plugin, backend, and frontend

#### Scenario: Root compose adds game-service
- **WHEN** `docker compose up` is run
- **THEN** the `game-service` service defined in the root `docker-compose.yaml` SHALL start alongside the included external services and depend on `dragncards-backend`

### Requirement: Infra compose provides Valkey
The repository SHALL define a separate infra compose stack for shared support services such as Valkey.

#### Scenario: Infra compose includes Valkey
- **WHEN** `docker-compose.infra.yaml` is parsed
- **THEN** it SHALL define a `valkey` service that game-service can use for session coordination

#### Scenario: Infra compose is started before the app stack
- **WHEN** the infra startup script is run
- **THEN** it SHALL start the infra compose stack before the main application stack so Valkey is available first

### Requirement: External compose is independently usable
The external compose file at `external/docker/docker-compose.yaml` SHALL be runnable on its own to bring up the DragnCards stack without the Game Service.

#### Scenario: External compose standalone startup
- **WHEN** a developer runs `docker compose -f external/docker/docker-compose.yaml up -d` from the repo root
- **THEN** postgres, mc-plugin, backend, and frontend SHALL start successfully without requiring game-service
