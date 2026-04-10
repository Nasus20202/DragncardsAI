## 1. Project Setup & Infrastructure

- [ ] 1.1 Initialize Python project structure at `services/game-service/` with `pyproject.toml`, `src/` package, and `tests/` directory
- [ ] 1.2 Add git submodule for `dragncards-mc-plugin` at `plugins/dragncards-mc-plugin/`
- [ ] 1.3 Create `docker/docker-compose.yml` with DragnCards backend (Elixir/Phoenix) and PostgreSQL services, based on upstream DragnCards compose config
- [ ] 1.4 Create setup script that starts DragnCards via Docker, creates a dev user, and installs the Marvel Champions plugin into the DragnCards instance
- [ ] 1.5 Verify DragnCards is accessible and a game can be created manually via the browser UI

## 2. Phoenix Channels WebSocket Client

- [ ] 2.1 Implement a minimal Python Phoenix Channels client: WebSocket connection, Phoenix message format serialization/deserialization (`[join_ref, ref, topic, event, payload]`)
- [ ] 2.2 Implement Phoenix heartbeat mechanism (periodic `heartbeat` messages to keep connection alive)
- [ ] 2.3 Implement channel join/leave with reply handling (join a topic, wait for `phx_reply`)
- [ ] 2.4 Implement push/receive pattern: send an event on a channel and await the response
- [ ] 2.5 Add connection loss detection and reconnection logic
- [ ] 2.6 Write integration tests against a running DragnCards instance: connect, join lobby, verify heartbeat

## 3. Game Session Management

- [ ] 3.1 Implement `SessionManager` class that maintains a pool of active game sessions (session ID -> WebSocket connection + cached state)
- [ ] 3.2 Implement session creation: connect to DragnCards, authenticate, create a game room, load the specified plugin, and join as a player
- [ ] 3.3 Implement session state tracking: listen for game state broadcasts on the channel and cache the latest state
- [ ] 3.4 Implement session deletion: leave the channel, close WebSocket, remove from session pool
- [ ] 3.5 Implement session listing: return metadata for all active sessions
- [ ] 3.6 Write integration tests: create session, verify state received, delete session

## 4. Game Action Translation

- [ ] 4.1 Research DragnCards WebSocket message format for game actions by inspecting the browser client's network traffic (card moves, phase changes, etc.)
- [ ] 4.2 Define a Python action model/schema for supported game actions (move card, change card property, advance phase, etc.)
- [ ] 4.3 Implement action translator: convert Python action objects into DragnCards WebSocket messages
- [ ] 4.4 Implement action execution: send action via WebSocket, wait for state update, return new state
- [ ] 4.5 Implement error handling for invalid actions (action rejected by DragnCards engine)
- [ ] 4.6 Write integration tests: execute card movements, phase transitions, verify state changes

## 5. HTTP REST API (FastAPI)

- [ ] 5.1 Set up FastAPI application with CORS, error handlers, and health check endpoint
- [ ] 5.2 Implement `POST /games` endpoint: create a new game session with specified plugin
- [ ] 5.3 Implement `GET /games` endpoint: list active game sessions
- [ ] 5.4 Implement `GET /games/{id}/state` endpoint: return current game state for a session
- [ ] 5.5 Implement `POST /games/{id}/actions` endpoint: execute a game action and return resulting state
- [ ] 5.6 Implement `DELETE /games/{id}` endpoint: end a game session
- [ ] 5.7 Add request/response models (Pydantic) for all endpoints
- [ ] 5.8 Write API tests using FastAPI test client against a running DragnCards instance

## 6. MCP Server Integration

- [ ] 6.1 Add Python MCP SDK dependency and set up MCP server alongside FastAPI in the same process
- [ ] 6.2 Implement `create_game` MCP tool: creates a game session, returns session ID and metadata
- [ ] 6.3 Implement `list_games` MCP tool: returns active game sessions
- [ ] 6.4 Implement `get_game_state` MCP tool: returns game state formatted as structured text for LLM consumption
- [ ] 6.5 Implement `execute_action` MCP tool: executes a game action and returns resulting state
- [ ] 6.6 Implement `delete_game` MCP tool: ends a game session
- [ ] 6.7 Implement `game://{session_id}/state` MCP resource for state retrieval
- [ ] 6.8 Add tool parameter schemas (JSON Schema) with descriptive documentation for each tool
- [ ] 6.9 Test MCP tools using an MCP client (e.g., mcp CLI inspector) against a running instance

## 7. End-to-End Validation

- [ ] 7.1 Write an end-to-end test: create a Marvel Champions game via HTTP API, query state, execute a sequence of actions (draw card, play card, end phase), verify state transitions
- [ ] 7.2 Write an end-to-end test: perform the same sequence via MCP tools
- [ ] 7.3 Test concurrent HTTP and MCP access to the same game session
- [ ] 7.4 Add Docker Compose configuration to run the Game Service alongside DragnCards for integrated deployment
