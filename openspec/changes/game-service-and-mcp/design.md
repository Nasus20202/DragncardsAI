## Context

DragnCards is a multiplayer online card game platform built with Elixir/Phoenix (backend) and React (frontend). Games are defined by plugins consisting of JSON files (game definition, including DragnLang automation scripts) and TSV files (card data). The game engine -- state management, card operations, DragnLang interpreter, phase/round logic -- is implemented entirely in the Elixir backend. All game state lives in DragnCards; we do not reimplement any of it.

We are building an LLM bot that plays Marvel Champions on DragnCards. This change delivers one foundational component: a Python Game Service that provides both an HTTP REST API and MCP tools, connecting to DragnCards as a headless WebSocket client.

The Marvel Champions plugin (`dragncards-mc-plugin`) is included as a git submodule and installed into the DragnCards instance during setup.

## Goals / Non-Goals

**Goals:**

- Provide a single Python service with two interfaces:
  - HTTP REST API (FastAPI) for programmatic game interaction (scripts, tests, future UI)
  - MCP tools/resources (Python MCP SDK) for LLM clients
- Connect to DragnCards via Phoenix Channels (WebSocket), acting as a headless player client
- Support loading any DragnCards-compatible plugin, starting with Marvel Champions
- Run DragnCards backend + PostgreSQL via Docker Compose as a dependency
- Include the MC plugin as a git submodule for reproducible setup

**Non-Goals:**

- Modifying the upstream DragnCards codebase
- Reimplementing the DragnCards game engine in Python (DragnCards manages all game state and logic)
- Building an LLM move generation service (future component)
- Building an orchestrator or UI (future components)
- Multi-game support beyond Marvel Champions in this iteration (architecture supports it, but testing/validation is MC-only)
- Multiplayer bot vs bot scenarios (single-player solo mode first)

## Decisions

### 1. Run DragnCards as a Docker dependency (not reimplement the engine)

**Decision**: Run the full DragnCards backend (Elixir/Phoenix + PostgreSQL) in Docker, rather than extracting or reimplementing game logic.

**Rationale**: The DragnCards game engine is deeply integrated with Elixir/OTP. DragnLang (the plugin scripting language), game state management via GenServer processes, and card interaction logic are all server-side Elixir. Reimplementing this in Python would be a massive, error-prone effort that duplicates upstream work. Wrapping via WebSocket is the natural integration point -- it's exactly how the browser client works.

**Alternatives considered**:
- *Extract Elixir game logic as a library*: Too tightly coupled to Phoenix; would require forking DragnCards.
- *Reimplement engine in Python*: Prohibitive effort, would diverge from upstream.

### 2. Single Python service with dual interfaces (HTTP + MCP)

**Decision**: One Python service exposes both a FastAPI HTTP API and MCP tools/resources via the Python MCP SDK. Both share the same underlying WebSocket session management.

**Rationale**: The HTTP API and MCP tools operate on the same data (game sessions, state, actions). Keeping them in one process eliminates inter-service HTTP calls, a second language/runtime (Node.js), and deployment complexity. The Python MCP SDK is mature enough for production use. The HTTP API serves non-LLM clients (test scripts, future UI, debugging), while MCP serves LLM clients.

**Alternatives considered**:
- *Separate Node.js MCP server*: Would add a second service, a second language, and inter-service communication overhead for what is essentially a thin proxy layer.
- *MCP only (no HTTP API)*: Would prevent non-LLM clients from interacting with games. HTTP API is valuable for testing, debugging, and future UI.

### 3. WebSocket client via Phoenix Channels

**Decision**: The Game Service connects to DragnCards using the Phoenix Channels WebSocket protocol, joining game rooms as a player.

**Rationale**: This is the same protocol the browser frontend uses. It gives us access to the full game API: creating/joining rooms, executing game actions, receiving real-time state updates. No DragnCards modifications needed.

**Implementation detail**: We'll use a Python Phoenix Channels client library (or implement a minimal one) to handle the WebSocket connection, channel joining, and message protocol (phoenix message format: `[join_ref, ref, topic, event, payload]`).

### 4. Session-based WebSocket management

**Decision**: The Game Service maintains in-memory game sessions. Each session holds a WebSocket connection to a DragnCards game room and caches the latest game state received from the server.

**Rationale**: The service needs to track WebSocket connections between API/MCP calls (the LLM makes one action at a time). Each session corresponds to one DragnCards game room. Both HTTP and MCP interfaces access the same session pool.

**API structure (HTTP)**:
- `POST /games` -- Create a new game session (creates room in DragnCards, loads plugin)
- `GET /games` -- List active sessions
- `GET /games/{id}/state` -- Get current game state
- `POST /games/{id}/actions` -- Execute a game action
- `DELETE /games/{id}` -- End a game session

**MCP tools**: Mirror the HTTP endpoints as tool calls (`create_game`, `list_games`, `get_game_state`, `execute_action`, `delete_game`).

### 5. Plugin management via git submodules

**Decision**: Include `dragncards-mc-plugin` as a git submodule, with a setup script that installs it into the DragnCards instance.

**Rationale**: Reproducible setup. The plugin needs to be uploaded to DragnCards via its plugin API or database seeding. A git submodule pins the exact version and a setup script automates installation.

### 6. Project structure

**Decision**: Organize as a monorepo with the service and infrastructure at the top level.

```
DragncardsAI/
  plugins/
    dragncards-mc-plugin/     # git submodule
  services/
    game-service/             # Python (FastAPI + MCP)
      src/
      tests/
      pyproject.toml
  docker/
    docker-compose.yml        # DragnCards + PostgreSQL
  openspec/                   # existing
```

## Risks / Trade-offs

- **[Phoenix Channels protocol complexity]** The Phoenix WebSocket protocol has specific message formats and heartbeat requirements. -> Mitigation: Use an existing Python Phoenix Channels client library, or implement a minimal client based on the well-documented protocol spec. Start with manual testing against a running DragnCards instance.

- **[DragnCards API stability]** DragnCards is an active project; WebSocket message formats may change. -> Mitigation: Pin to a specific DragnCards version via Docker image tag. Wrap all protocol interaction in an abstraction layer.

- **[Game state complexity]** DragnCards game state is a large nested structure (cards, groups, players, counters, phases). The service needs to parse and present this meaningfully. -> Mitigation: Start with exposing the raw state, then iteratively build game-state summarization for LLM consumption in the MCP layer.

- **[Plugin installation automation]** Installing a plugin into DragnCards requires either API calls (authenticated) or database seeding. -> Mitigation: Use the DragnCards "Update Plugin via API" endpoint, or seed via Elixir scripts during Docker setup.

- **[Single process dual interface]** Running both FastAPI and MCP server in one process adds some complexity. -> Mitigation: FastAPI and the MCP SDK can coexist in the same async Python process. MCP can run as stdio transport (for local LLM clients) or SSE transport (for remote clients), alongside the HTTP server.
