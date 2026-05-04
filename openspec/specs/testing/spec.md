# Testing Spec

## Purpose

This spec defines the functional testing requirements for the Game Service. The test suite SHALL focus on externally observable behavior and supported workflows rather than internal implementation details, and it SHALL cover those behaviors with both unit and integration tests.

## Requirements

### Requirement: Functional coverage at multiple test layers
The Game Service test suite SHALL cover supported functionality with both unit tests and integration tests. Unit tests SHALL verify behavior in isolation, and integration tests SHALL verify live behavior where network protocols, external dependencies, or interoperability matter.

#### Scenario: Functional behavior covered by unit tests
- **WHEN** a Game Service behavior can be validated without network access or external processes
- **THEN** the test suite SHALL cover that behavior with unit tests using in-process fakes, mocks, or fixtures

#### Scenario: Functional behavior covered by integration tests
- **WHEN** a Game Service behavior depends on DragnCards, WebSocket communication, HTTP transport, or MCP interoperability
- **THEN** the test suite SHALL cover that behavior with integration tests against the local stack

### Requirement: Unit test isolation
Unit tests SHALL run without any network access, running DragnCards instance, or external services.

#### Scenario: Unit tests run offline
- **WHEN** the unit test suite is executed with no DragnCards or network available
- **THEN** all unit tests SHALL pass

#### Scenario: Unit tests require no live setup
- **WHEN** unit tests are collected and run
- **THEN** they SHALL not require live sockets, live HTTP services, or external database setup

### Requirement: Unit coverage for protocol and action behavior
Unit tests SHALL verify the functional contracts for message handling, state-update handling, and action payload generation without requiring a live DragnCards connection.

#### Scenario: Phoenix message data round-trips correctly
- **WHEN** Phoenix wire-format message data is serialized and deserialized in unit tests
- **THEN** the message fields and payload content SHALL round-trip without loss for supported payload shapes

#### Scenario: Connection targets are derived correctly
- **WHEN** the service prepares a Phoenix connection using a socket URL and optional authentication token
- **THEN** the resulting connection target SHALL contain the expected websocket path and authentication query parameters

#### Scenario: State-bearing events are recognized correctly
- **WHEN** the service receives a mix of room events in unit tests
- **THEN** state-bearing events SHALL be recognized as state updates and non-state events SHALL remain separate from state refresh handling

#### Scenario: Supported actions produce valid DragnCards payloads
- **WHEN** a supported action is translated in unit tests
- **THEN** the resulting payload SHALL preserve the requested game intent, include required metadata, and reject invalid input combinations

### Requirement: Unit coverage for interface behavior
Unit tests SHALL verify the functional behavior of the Game Service HTTP and MCP interfaces without requiring a live DragnCards instance.

#### Scenario: Public operations are discoverable
- **WHEN** unit tests inspect the generated HTTP or MCP interface metadata
- **THEN** the supported operations SHALL be discoverable with non-empty descriptions and machine-readable schemas

#### Scenario: Invalid input yields descriptive errors
- **WHEN** unit tests exercise invalid session identifiers, unsupported actions, or malformed requests
- **THEN** the service SHALL return descriptive errors through its HTTP or MCP response contract

#### Scenario: State responses remain usable when no state is available
- **WHEN** unit tests request formatted state output for a session with missing or unavailable state
- **THEN** the returned response SHALL remain well-formed and explain that no current state is available

### Requirement: Integration test structure
Integration tests SHALL require a running DragnCards instance and SHALL validate live behavior without leaking state between tests.

#### Scenario: Integration tests fail clearly without dependencies
- **WHEN** integration tests are run without a reachable DragnCards instance
- **THEN** the tests SHALL fail with a clear dependency error rather than a silent pass or ambiguous assertion failure

#### Scenario: Integration tests clean up created sessions
- **WHEN** an integration test creates a game session
- **THEN** the session SHALL be deleted in teardown so later tests start from a clean state

### Requirement: Integration coverage for live DragnCards connectivity
Integration tests SHALL verify that the Game Service can establish and maintain the live connection behaviors it depends on.

#### Scenario: Service connects to DragnCards successfully
- **WHEN** the service authenticates and opens a Phoenix websocket connection to DragnCards
- **THEN** the connection SHALL be established and usable for room operations

#### Scenario: Heartbeat keeps a live connection healthy
- **WHEN** a connection remains open across multiple heartbeat intervals
- **THEN** the connection SHALL remain alive and continue to accept room operations

#### Scenario: Room channels can be joined and left
- **WHEN** the service joins and later leaves a room channel in an integration test
- **THEN** the join and leave workflow SHALL succeed through the live Phoenix channel

### Requirement: Integration coverage for session lifecycle and state access
Integration tests SHALL verify the externally visible session lifecycle and state retrieval workflows.

#### Scenario: Session creation returns usable metadata
- **WHEN** a client creates a game session for a supported plugin
- **THEN** the service SHALL return a non-empty session identifier, plugin metadata, and room metadata

#### Scenario: Newly created session exposes current state
- **WHEN** a client requests state for a newly created session
- **THEN** the service SHALL return current game state data including the game payload

#### Scenario: Active sessions are listed
- **WHEN** a client lists active sessions after creating a session
- **THEN** the created session SHALL appear in the returned session list

#### Scenario: Unknown sessions are rejected
- **WHEN** a client requests state or other session operations for an unknown session identifier
- **THEN** the service SHALL return a not-found error through the relevant interface

#### Scenario: Session deletion removes access
- **WHEN** a client deletes an active session
- **THEN** the session SHALL be removed from the active pool and subsequent access SHALL fail as not found

#### Scenario: Unknown plugins are rejected at creation time
- **WHEN** a client requests a game session for a plugin that is not configured
- **THEN** the service SHALL reject the request with a descriptive validation error

### Requirement: Integration coverage for action, room-control, and room-event workflows
Integration tests SHALL verify that the Game Service exposes the gameplay and room-management functionality promised by its public API.

#### Scenario: Gameplay actions update observable state
- **WHEN** a client executes a supported gameplay action against an active session
- **THEN** the returned or subsequently fetched state SHALL reflect that action's effect

#### Scenario: Room-control operations succeed through the public API
- **WHEN** a client invokes supported room-control operations such as reset, seat assignment, spectator changes, alert broadcast, replay save, or room close
- **THEN** the Game Service SHALL perform the requested operation or return a descriptive error if the session is invalid

#### Scenario: Room-event observation returns captured data
- **WHEN** alert or GUI-update events are produced for an active session
- **THEN** the corresponding room-event endpoints or resources SHALL expose the captured data in a consumable format

### Requirement: Integration coverage for HTTP and MCP interfaces
Integration and end-to-end tests SHALL verify that both public interfaces expose consistent functionality.

#### Scenario: Core lifecycle works through HTTP
- **WHEN** a client creates a game, queries state, executes an action, and deletes the game through HTTP
- **THEN** each operation SHALL succeed in sequence and the deleted session SHALL no longer be accessible

#### Scenario: Core lifecycle works through MCP
- **WHEN** an MCP client creates a game, queries state, executes an action, lists sessions, and deletes the game
- **THEN** each operation SHALL succeed through MCP with valid responses

#### Scenario: HTTP and MCP observe the same shared state
- **WHEN** one interface mutates an active session and the other interface reads that same session
- **THEN** both interfaces SHALL observe the same updated session state

#### Scenario: HTTP and MCP can access the same session concurrently
- **WHEN** HTTP and MCP clients query or operate on the same session concurrently
- **THEN** both interfaces SHALL return valid responses for that shared session

### Requirement: Test environment configuration
Integration tests SHALL read their connection parameters from environment variables with sensible defaults for local development.

#### Scenario: Environment variable defaults
- **WHEN** environment variables `DRAGNCARDS_HTTP_URL`, `DRAGNCARDS_WS_URL`, `DEV_USER_EMAIL`, and `DEV_USER_PASSWORD` are not set
- **THEN** tests SHALL default to `http://localhost:4000`, `ws://localhost:4000/socket`, `dev_user@example.com`, and `password` respectively

#### Scenario: Plugin registry configuration
- **WHEN** `MC_PLUGIN_ID` and `MC_PLUGIN_VERSION` environment variables are not set
- **THEN** the integration test plugin registry SHALL default to plugin ID `1` and version `3` for `marvel-champions`
