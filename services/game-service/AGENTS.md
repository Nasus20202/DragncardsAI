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

## DragnCards credential cache

`dragncards/auth_cache.py` caches the bot's DragnCards session token and numeric
user id in the session-store Valkey under
`game-service:dragncards-auth:<sha256(url + NUL + email)[:32]>`, because deriving
them cost ~305 ms of a ~590 ms `POST /games` and was repeated for every room
(DRA-36). It follows the agent-orchestrator model cache
(`integrations/bifrost.py`) — `GET`/`SETEX`, JSON value, namespaced key.

Three things must stay true when touching it:

- **The token is a credential.** It belongs in exactly two places: the JSON value
  written to Valkey, and the `authorization` header of a DragnCards request. Never
  a log record, never a span attribute, never an exception message, never a spec or
  README example. This is why the RESP client's `db.operation.name` attribute
  records `parts[0]` only — the cache depends on command arguments never reaching a
  span, so do not widen that.
- **A Valkey failure degrades, it does not fail.** Every command is wrapped; a
  miss, a transport error, or a stored value of the wrong shape is reported to the
  caller as a miss and the credential is derived live. This service opens a fresh
  TCP connection per command, so a reset is a real possibility, not a hypothetical
  (DRA-35).
- **The TTL is chosen against the token's own lifetime, not guessed.** DragnCards
  issues into `Pow.Store.CredentialsCache`, declared with 30 minutes upstream and
  not extended on use, so the default `DRAGNCARDS_AUTH_CACHE_TTL_SECONDS=900` is
  half of it. If you change the default, say what lifetime you checked it against.

The room channel is the only place the credential is actually validated on this
path — `POST /api/v1/games` is not behind the authenticated pipeline upstream and
accepts any token — so a forgotten credential surfaces as a `room_unavailable`
push on join, which evicts a cached entry. `PhoenixClient.join` registers the
Channel *before* awaiting the join reply for that reason: the receive loop is a
separate task and would otherwise deliver the room's opening broadcasts to a topic
`_dispatch` does not yet know, dropping them silently.

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

### Seats

A seat is a **slot**, not an identity. `player1`..`player4` are keys of one map in
the room's server process, and the seat an action acts as comes from the action's
own `player_n` (`options.player_ui.playerN` on the wire) — never from the user the
websocket authenticated as. So one credential drives all four seats and a
multi-player game needs no second DragnCards account.

Two rules follow, and both have bitten:

- An action whose DragnLang touches `$PLAYER_N` and carries no `player_n` fails
  with `Variable $PLAYER_N is undefined`. There is no default seat at the
  DragnCards end. Prebuilt hero decks load into `playerNDeck` /
  `playerNNemesisSet`, so a deck load without the right seat silently fills the
  wrong seat's groups.
- Seat *occupancy* is what names a seat in the game log, and Marvel Champions
  omits a seat's draw line altogether when the seat has no alias. An unclaimed
  seat is missing from the recorded game, not just unnamed — so seats are claimed
  to match the player count. Anything reducing when seats are claimed has to
  account for that.

`set_seat` addresses a seat by its seat id string, never by an index; an index
writes a map key no seat lookup will find. `logic/seats.py` owns this vocabulary —
use it rather than re-deriving seat handling at a call site.

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