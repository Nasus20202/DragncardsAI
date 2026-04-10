## Why

We want to build an LLM-powered bot that can play card games on the DragnCards platform. The first target game is Marvel Champions. To enable this, we need a programmatic interface to the DragnCards game engine -- currently the only way to interact with it is through the browser-based UI. We need a single service that provides both an HTTP API (for scripts, tests, and future UI) and MCP tools (for LLM clients) to interact with the game. This is the minimum viable piece to let both humans and LLMs programmatically observe and act within a DragnCards game.

## What Changes

- Add a **Game Service** -- a single Python service that connects to the DragnCards backend via Phoenix Channels (WebSocket), acting as a headless player client. It exposes two interfaces:
  - **HTTP REST API** (FastAPI) for game session management, state queries, and action execution -- usable by scripts, tests, and future components
  - **MCP tools/resources** (Python MCP SDK) for LLM clients to interact with games via the Model Context Protocol
- The service manages WebSocket connections to DragnCards game rooms, translates API/MCP calls into Phoenix Channel messages, and returns game state.
- DragnCards (Elixir/Phoenix) manages all game state, logic, and automation -- we do not reimplement or modify any of it. It runs as a Docker dependency.
- The Marvel Champions plugin (`dragncards-mc-plugin`) is included as a git submodule and installed into the DragnCards instance during setup.

## Capabilities

### New Capabilities

- `game-service`: Single Python service wrapping the DragnCards game engine. Connects via Phoenix Channels WebSocket. Exposes both HTTP REST API and MCP tools/resources. Manages WebSocket sessions, plugin loading, game state queries, and action execution.

### Modified Capabilities

(none -- this is a greenfield project)

## Impact

- **New service**: One new Python service (`game-service`) to be built in this repository, exposing both HTTP and MCP interfaces.
- **External dependencies**: Requires a running DragnCards instance (Elixir/Phoenix backend + PostgreSQL, via Docker Compose). Requires the Marvel Champions plugin (`dragncards-mc-plugin`) to be installed in the DragnCards instance.
- **APIs**: New HTTP API surface (FastAPI). New MCP tool/resource surface (Python MCP SDK).
- **Future components**: This lays the foundation for a future LLM service (move generation), orchestrator, and UI -- but those are out of scope for this change.
