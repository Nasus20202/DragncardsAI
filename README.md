# DragncardsAI

An LLM-powered bot that plays **Marvel Champions** on [DragnCards](https://github.com/seastan/dragncards).

## Quick start

```bash
make up
# or
docker compose up -d
```

| Service            | URL                             |
| ------------------ | ------------------------------- |
| Frontend           | http://localhost:3000           |
| Backend API        | http://localhost:4000           |
| Game Service       | http://localhost:4001           |
| Agent Orchestrator | http://localhost:4002           |
| Dashboard          | http://localhost:3001           |
| Bifrost AI-Gateway | http://localhost:4003           |
| Grafana            | http://localhost:3004           |
| Login              | dev_user@example.com / password |

## Architecture

```mermaid
flowchart LR
    classDef dragncards fill:#4a90e2,color:#fff
    classDef ai fill:#722ed1,color:#fff
    classDef infra fill:#52c41a,color:#fff
    classDef external fill:#fa8c16,color:#fff

    Frontend["dragncards-frontend<br/>port 3000"]
    Backend["dragncards-backend<br/>port 4000"]
    PG1["dragncards-postgres<br/>port 5440"]
    GameSvc["game-service<br/>port 4001"]
    OrcPg["agent-orchestrator-postgres<br/>port 5441"]
    AgentOrch["agent-orchestrator<br/>port 4002"]
    Dashboard["dashboard<br/>port 3001"]
    Bifrost["bifrost<br/>port 4003"]
    OtelLGTM["otel-lgtm<br/>port 3004"]
    Valkey1["game-service-valkey<br/>port 6380"]
    Valkey2["agent-orchestrator-valkey<br/>port 6381"]
    HostLM["LMStudio<br/>host.docker.internal:1234"]
    ExtAI["External AI Providers"]

    class Frontend,Backend,PG1 dragncards
    class GameSvc,AgentOrch,Dashboard ai
    class Bifrost,OtelLGTM,Valkey1,Valkey2,OrcPg infra
    class HostLM,ExtAI external

    Frontend --> Backend --> PG1
    Dashboard --> AgentOrch
    Dashboard --> GameSvc

    AgentOrch --> GameSvc
    AgentOrch --> Bifrost
    AgentOrch --> OrcPg
    AgentOrch --> Valkey2

    GameSvc --> Backend
    GameSvc --> Valkey1

    Bifrost --> HostLM
    Bifrost --> ExtAI

    OtelLGTM -.- GameSvc
    OtelLGTM -.- AgentOrch
    OtelLGTM -.- Dashboard
    OtelLGTM -.- Bifrost
```

The system runs DragnCards (frontend + backend) with PostgreSQL. The game-service connects to DragnCards via HTTP/WebSocket to automate Marvel Champions gameplay. The agent-orchestrator manages AI sessions with its own PostgreSQL and Valkey, using Bifrost as an AI gateway that routes to local LMStudio or external providers. The dashboard provides a UI for interacting with both services. All services send telemetry to otel-lgtm for observability.

## Development

```bash
# List useful commands
make

# Lint and formatting validation
scripts/lint.sh
make lint

# Apply lint and formatting fixes where supported
scripts/lint.sh --fix
make lint-fix

# Unit tests (no network required)
scripts/test.sh unit
make test-unit

# Integration tests (requires Docker stack running)
scripts/test.sh integration
make test-integration

# Rebuild images
scripts/docker.sh build
make build
```
