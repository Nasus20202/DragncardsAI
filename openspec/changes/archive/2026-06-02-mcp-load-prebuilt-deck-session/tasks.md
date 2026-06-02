## 1. Deck Loading Support

- [x] 1.1 Add Marvel Champions prebuilt deck lookup/load helpers that resolve a deck id to the plugin's load payload.
- [x] 1.2 Add a session-scoped deck loading entrypoint that reuses the existing game-session execution path.

## 2. MCP Exposure

- [x] 2.1 Add the MCP tool `load-prebuilt-deck` for loading a prebuilt deck into an existing session.
- [x] 2.2 Ensure the tool is scoped to a target session id and uses the selected deck id as input.

## 3. Tests

- [x] 3.1 Add unit tests for deck lookup and successful session loading behavior.
- [x] 3.2 Add failure-path tests for invalid deck ids and missing sessions.
- [x] 3.3 Update MCP discovery tests to include the new prebuilt deck loading tool.
