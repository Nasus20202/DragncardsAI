# Game Service Agent Guide

Read this file before making changes in `services/game-service/`.

## Scope

These instructions apply to the game-service and override the repository-level `AGENTS.md`.

## Tech Stack

- **Language**: Python 3.x with `uv` package manager
- **Framework**: FastAPI for HTTP API, Starlette for ASGI
- **MCP**: Model Context Protocol server mounted at `/mcp`
- **WebSocket**: Phoenix Channels for DragnCards communication
- **Testing**: pytest with async support

## Project Structure

```
game-service/
  src/game_service/       # Main source code
  tests/                  # Unit and integration tests
```

## Working Rules

- Use `uv run` to execute commands in the service directory
- Follow existing async/await patterns throughout
- Use Pydantic models for request/response validation
- Keep MCP tools and HTTP endpoints consistent in behavior
- Phoenix Channel messages are defined in DragnCards protocol

## DragnCards Concepts

### Session Management

- Sessions are created via `POST /games` with a plugin name
- Sessions can attach to existing rooms via `POST /games/attach`
- Each session maintains a Phoenix Channel connection

### Actions

Common action types executed via `POST /games/{session_id}/actions`:
- `next_step`, `prev_step` - Navigate game flow
- `draw_card`, `move_card` - Card manipulation
- `set_card_property` - Modify card state
- `set_player_count` - Change player configuration
- `load_cards`, `unload_cards` - Manage card pools
- `raw` - Direct DragnLang execution

### State Model

Game state includes:
- Zone structures (player zones, encounter deck, etc.)
- Card arrays with properties
- Prompt information for current interactions
- Player/seat assignments

## Testing

```bash
uv run pytest tests/unit/ -v              # Unit tests
uv run pytest tests/integration/ -v       # Integration tests
uv run pytest tests/ -v                  # All tests
```

## Commands

```bash
uv run game-service         # Start service
uv run pytest               # Run tests
```

## Agent Guidance

1. Study existing action implementations in `src/game_service/`
2. DragnLang actions should be validated against the game engine
3. MCP tools must match HTTP endpoint functionality
4. Handle Phoenix Channel errors gracefully with reconnect logic