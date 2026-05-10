# DragncardsAI

An LLM-powered bot that plays **Marvel Champions** on [DragnCards](https://github.com/seastan/dragncards).

## Quick start

```bash
cd docker
docker compose up -d
```

| Service      | URL                             |
| ------------ | ------------------------------- |
| Frontend     | http://localhost:3000           |
| Backend API  | http://localhost:4000           |
| Game Service | http://localhost:8000           |
| Dashboard    | http://localhost:3020           |
| Login        | dev_user@example.com / password |

## Development

```bash
# Unit tests (no network required)
scripts/test.sh unit

# Integration tests (requires Docker stack running)
scripts/test.sh integration

# Rebuild images
scripts/docker.sh build
```

## Dashboard

The dashboard lives in `services/dashboard` and uses `pnpm`.

```bash
cd services/dashboard
pnpm install
pnpm dev
```

Default local URLs expected by the dashboard:

- `AGENT_ORCHESTRATOR_URL=http://localhost:8010`
- `GAME_SERVICE_URL=http://localhost:8000`
- `DRAGNCARDS_FRONTEND_URL=http://localhost:3000`

Default session configuration is environment-backed:

- `DASHBOARD_DEFAULT_PROVIDER_ID`
- `DASHBOARD_DEFAULT_MODEL_NAME`
- `DASHBOARD_DEFAULT_GAME_PLUGIN`
- `DASHBOARD_DEFAULT_GAME_SERVICE_MCP_ENABLED`
- `DASHBOARD_DEFAULT_GAME_SERVICE_MCP_NAME`
- `DASHBOARD_DEFAULT_GAME_SERVICE_MCP_TRANSPORT`
- `DASHBOARD_DEFAULT_GAME_SERVICE_MCP_URL`
- `DASHBOARD_DEFAULT_SKILLS`
- `DASHBOARD_DEFAULT_CUSTOM_MCPS_JSON`
- `AGENT_ORCHESTRATOR_OPENAPI_PATH`
- `GAME_SERVICE_OPENAPI_PATH`

Useful commands:

```bash
cd services/dashboard
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```
