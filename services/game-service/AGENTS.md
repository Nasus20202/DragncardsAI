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

## Browser CORS

`CORS_ALLOW_ORIGINS` is a comma-separated allowlist of browser origins, read in
`api/app.py` (this service has no `Settings` class; `main.py` reads `os.environ`
the same way) and defaulting to the local dashboard. **Never widen it to `*`.**
That is what this service shipped with, behind a comment conceding it was a
development shortcut, and because Compose publishes 4001 on the host it meant any
page a developer visited could drive a cross-origin `DELETE /games/{session_id}`
or the mutating action routes (DRA-31). The policy is pinned at the wire level in
`tests/unit/test_cors.py`.

Two things to hold on to when touching this:

- **A request with no `Origin` must keep working.** That is every real caller: the
  dashboard reaches this service through its own server-side Node proxy, the
  orchestrator and history-service are server-to-server, MCP clients are not
  browsers, and this service's own `/docs` playground is same-origin, which CORS
  never applies to.
- **CORS is not authentication.** It only stops a *browser* being used as a
  confused deputy for preflighted methods. Any non-browser client omits `Origin`
  and is unaffected. Requiring a credential is DRA-32, deliberately separate.

## MCP surface

`mcp/server.py` derives the MCP tools from this service's own FastAPI OpenAPI schema, so
a tool *is* the endpoint it came from and a tool's name is that endpoint's
`operation_id`. There is no hand-written tool layer, which is why MCP and HTTP cannot
drift: **adding a route adds a tool automatically, so give every route an explicit
`operation_id`** or the tool inherits FastAPI's generated
`get_game_state_games__session_id__state_get` style name.

The `route_maps` list in `mcp/server.py` is what a route is kept *out* with, and it is the
security surface: this service has no authentication, so anything left in is something a
model can invoke on a running deployment. Excluded here: `/health`, snapshot
import/export, the room-control and room-observability routes, and the debug routes —
raw state, the generic `POST /actions`, and raw DragnLang. Exclusion applies to MCP only;
every one of those endpoints still works over HTTP for a developer who types it
deliberately.

The three Python services that came later do the same thing through
`dragncards_common.mcp`; this service predates that helper and keeps its own equivalent
copy, the same way it keeps its own telemetry bootstrap. The end-to-end loop these
surfaces exist for is documented in the root
[`AGENTS.md`](../../AGENTS.md#driving-the-system-end-to-end).

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