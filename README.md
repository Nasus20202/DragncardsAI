# DragncardsAI

An LLM-powered bot that plays **Marvel Champions** on [DragnCards](https://github.com/seastan/dragncards).

## Quick start

```bash
cd docker
docker compose up -d
```

| Service      | URL                             |
|--------------|---------------------------------|
| Frontend     | http://localhost:3000           |
| Backend API  | http://localhost:4000           |
| Game Service | http://localhost:8000           |
| Login        | dev_user@example.com / password |

## Game Service

REST API and MCP server that connects to DragnCards over Phoenix Channels WebSocket.

```
GET    /health
POST   /games                 create a session  {"plugin": "marvel-champions"}
GET    /games                 list sessions
GET    /games/{id}/state      current game state
POST   /games/{id}/actions    execute an action
DELETE /games/{id}            end a session
```

MCP tools (`create_game`, `list_games`, `get_game_state`, `execute_action`, `delete_game`) are configured in `opencode.jsonc` and available automatically when the stack is running.

## Development

```bash
# Unit tests (no network required)
cd services/game-service
python -m pytest tests/unit/ -v

# Rebuild images
cd docker
docker compose build
```
