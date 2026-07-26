# Game Service

`game-service` is the DragnCards-facing service.

It does two things:
- exposes an HTTP API for creating and controlling game sessions
- exposes a focused subset of those capabilities over MCP so LLM clients can call tools directly

The service talks to DragnCards over Phoenix Channels and keeps a local session pool.

## Run

From the repo root:

```bash
scripts/run.sh start game-service
```

Inside the service directory:

```bash
uv run game-service
```

Default local URL:

```text
http://localhost:4001
```

## What This Service Is For

Use `game-service` when you need to:
- create or attach to a DragnCards room
- inspect current game state
- execute DragnLang-backed game actions
- manage room-level behavior like seats, player count, alerts, and replay
- search plugin card catalogs
- expose game controls to an LLM through MCP

## Endpoint Guide

### Health and Capability Discovery

Use these first when integrating a client.

- `GET /health`
  Returns a simple liveness response.

- `GET /actions`
  Lists all generic typed actions and curated raw DragnLang operations.
  Use this when you want to know what can be passed to `POST /games/{session_id}/actions`.

### Session Lifecycle

Use these to create, attach, list, and remove active game sessions.

- `POST /games`
  Create a new game session for a plugin. The requesting user is seated in the
  first available player slot.

- `POST /games/attach`
  Attach to an existing DragnCards room. The requesting user is seated in the
  first available player slot.

- `GET /games`
  List active sessions managed by this service.

- `GET /games/by-slug/{room_slug}`
  Resolve a human-readable DragnCards room slug (e.g. `lively-fog-1234`) to its
  session metadata, including the canonical UUID `session_id`. This is a
  read-only lookup and the ONLY endpoint that accepts a room slug. All state,
  mutation, and delete endpoints remain UUID-only because the slug is
  low-entropy and guessable; use the returned `session_id` to address those
  endpoints.

- `DELETE /games/{session_id}`
  Delete a managed session.
  Optional query param: `close_room=true`.

### State and Snapshots

Use these when you need the current table state or a reusable snapshot.

- `GET /games/{session_id}/state`
  Get the latest game state.

- `GET /games/{session_id}/snapshot`
  Export a reusable snapshot document.

- `PUT /games/{session_id}/snapshot`
  Load a previously exported snapshot.

### Actions

Use these to discover session-specific actions and execute them.

- `GET /games/{session_id}/actions`
  List actions accepted by this session, including plugin metadata and load groups.

- `POST /games/{session_id}/actions`
  Execute one action.

Common action types include:
- `next_step`
- `prev_step`
- `draw_card`
- `move_card`
- `set_card_property`
- `set_player_count`
- `load_cards`
- `unload_cards`
- `raw`

### Room Control

Use these when you want to control the room rather than perform a normal game action.
These endpoints are HTTP-only and are not exposed through MCP.

- `POST /games/{session_id}/reset`
- `POST /games/{session_id}/seat`
- `POST /games/{session_id}/spectator`
- `POST /games/{session_id}/alert`
- `POST /games/{session_id}/replay`
- `POST /games/{session_id}/player-count`

### Room Observability

Use these to read room-side signals buffered by the session manager.

- `GET /games/{session_id}/alerts`
- `GET /games/{session_id}/gui-update`

### Card Search

Use these to query a plugin-specific card catalog.

Current pattern:
- `GET /cards/{provider_name}`

Example:

```text
GET /cards/marvel-champions?name=spider&type_code=hero
```

Provider-specific filters are defined by the provider itself.

## MCP

When `game-service` runs in HTTP mode, MCP is mounted at:

```text
/mcp
```

Example local MCP URL:

```text
http://localhost:4001/mcp
```

MCP tools expose a minimal game-control surface:

- `create_game`
- `attach_game`
- `list_games`
- `lookup_session_by_slug`
- `delete_game`
- `get_game_state`
- `get_session_actions`
- `execute_action`
- `list_actions`
- `list_card_providers`
- `search_cards_<provider>`

`lookup_session_by_slug` resolves a room slug to its session metadata, including
the canonical UUID `session_id`. The slug is accepted for lookup only; every
other tool and endpoint that reads, mutates, or deletes a session takes the UUID
`session_id`, never the slug.

Room control and observability endpoints (reset, seat assignment, spectator, alerts,
replay, player count, alert buffers, GUI updates) are HTTP-only.

## Typical Workflow

### Create and inspect a session

1. `POST /games`
2. `GET /games/{session_id}/state`
3. `GET /games/{session_id}/actions`

### Execute a game action

1. `POST /games/{session_id}/actions`
2. `GET /games/{session_id}/state`

### Search cards before loading them

1. `GET /cards/marvel-champions?...`
2. `POST /games/{session_id}/actions` with `load_cards`

## Tests

From the repo root:

```bash
scripts/test.sh unit game-service
scripts/test.sh integration game-service
```

From the service directory:

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
```
