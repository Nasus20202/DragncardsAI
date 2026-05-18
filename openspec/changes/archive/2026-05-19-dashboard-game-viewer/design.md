## Context

The dashboard originally exposed `Play` and `Swagger` sections only. There was no view for monitoring active DragnCards game sessions. `game-service` already exposes `GET /games`, and the DragnCards frontend can render a room directly from its room route.

## Goals / Non-Goals

**Goals:**
- Add a `Games` navigation entry to the dashboard shell
- Display a list of active game sessions from `game-service`
- Show an iframe that loads the DragnCards frontend for the selected room

**Non-Goals:**
- Game interaction from the dashboard
- Reimplementing DragnCards rendering in dashboard code
- Persistent game selection across reloads
- Live list refresh beyond the initial games fetch

## Decisions

### Decision: Create a dedicated `/games` route and workspace

The implementation follows the same high-level workspace shape as `/play`: a sidebar plus a main content area.

**Alternatives considered:**
- Embed the list inside Play: rejected because agent sessions and game sessions are separate concerns
- Use a modal or drawer: rejected because the iframe needs a full workspace area

### Decision: Use iframe embedding with the room route

The DragnCards frontend is embedded by pointing an iframe to `DRAGNCARDS_FRONTEND_URL/room/{room_slug}`.

**Alternatives considered:**
- Render game state directly in dashboard code: rejected because the upstream frontend already owns complex table rendering
- Proxy the frontend through a new service endpoint: rejected because direct iframe embedding is simpler

### Decision: Load games once from `GET /games`

The Games workspace fetches the active game list once on load and sorts the results by `created_at` descending.

**Alternatives considered:**
- Direct database reads: rejected because `game-service` already owns session lifecycle
- WebSocket or polling refresh for the game list: rejected for the shipped scope; the iframe itself handles live table state once a room is selected

### Decision: Expose frontend URL through dashboard config

`DRAGNCARDS_FRONTEND_URL` is exposed through the dashboard config API and consumed by the Games workspace.

**Alternatives considered:**
- Hardcode the frontend URL: rejected because environments vary

## Risks / Trade-offs

- **Iframe sizing**: the embedded frontend may not fit perfectly in all situations; the shipped implementation keeps the iframe simple and full-size within the workspace
- **Cross-origin restrictions**: the frontend must allow iframe embedding
