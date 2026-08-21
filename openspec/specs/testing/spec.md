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
Unit tests SHALL run without any network access, running game platform, or external services.

Unit tests SHALL also run without any game platform's content on disk. Importing the Game Service, building its application, and generating its OpenAPI document SHALL NOT require the Marvel Champions plugin JSON, a card database, a deck, or a scenario file to be present, because a platform's vocabularies are resolved lazily and per platform. A suite that only passes because one platform's files happen to be checked out is a suite that hides the coupling it exists to prevent.

#### Scenario: Unit tests run offline
- **WHEN** the unit test suite is executed with no game platform or network available
- **THEN** all unit tests SHALL pass

#### Scenario: Unit tests require no live setup
- **WHEN** unit tests are collected and run
- **THEN** they SHALL not require live sockets, live HTTP services, or external database setup

#### Scenario: Unit tests require no platform content on disk
- **WHEN** the unit test suite is executed with no plugin JSON, card database, deck, or scenario file present for any platform
- **THEN** the Game Service SHALL import, its application SHALL build, its OpenAPI document SHALL be generated, and all unit tests SHALL pass

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
Integration tests SHALL require a running instance of the game platform they exercise and SHALL validate live behavior without leaking state between tests.

An integration test SHALL name the platform it needs. A test that requires a platform which is not reachable SHALL fail, or skip with a stated reason, naming that platform and the setting it was reached by — never present as an unrelated assertion failure, and never pass vacuously.

#### Scenario: Integration tests fail clearly without dependencies
- **WHEN** integration tests are run without a reachable DragnCards instance
- **THEN** the tests SHALL fail with a clear dependency error rather than a silent pass or ambiguous assertion failure

#### Scenario: A missing marvel-lcg instance is reported as such
- **WHEN** the marvel-lcg integration tests are run with no reachable marvel-lcg instance, because its compose profile was not selected
- **THEN** the failure or skip SHALL name marvel-lcg and the base-URL setting it was reached by, and SHALL NOT report a generic connection or assertion error

#### Scenario: Integration tests clean up created sessions
- **WHEN** an integration test creates a game session on either platform
- **THEN** the session SHALL be deleted in teardown so later tests start from a clean state

### Requirement: Browser smoke coverage for chat-driven game creation
The test suite SHALL include a browser-driven smoke test implemented from the dedicated `services/smoketest` service that opens the dashboard Play workspace, submits a chat prompt asking the agent to create a Marvel Champions game, and verifies that the game is created in live DragnCards state.

The smoke test SHALL run against the documented local `llama.cpp` smoke-model configuration rather than requiring a hosted model provider.

#### Scenario: Chat prompt creates a game through the browser flow
- **WHEN** the smoke test opens the dashboard, submits the documented create-game prompt, and the job reaches a successful terminal state
- **THEN** the test SHALL verify that a corresponding game session or room was created and is observable through the supported local stack

#### Scenario: Verification tolerates asynchronous game creation
- **WHEN** the create-game request succeeds but DragnCards state is not visible immediately
- **THEN** the smoke test SHALL retry verification for a bounded interval before failing

#### Scenario: Smoke test fails clearly when local model runtime is unavailable
- **WHEN** the browser smoke test is run without a reachable `llama.cpp` smoke-model endpoint
- **THEN** the failure SHALL identify the missing local model dependency rather than reporting only a generic UI assertion failure

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
- **THEN** the corresponding room-event endpoints SHALL expose the captured data in a consumable format

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

Each supported game platform SHALL have its own variables, so that selecting a platform in a test run is configuration rather than a code change.

Integration suites that need a database SHALL keep the existing convention of creating a throwaway database named `<service>_test_<uuid>` per run, migrating it, and dropping it in teardown. A migration that adds a platform column SHALL be exercised through that same path, so the migration is proven against a real database engine and no test run inherits another run's schema.

#### Scenario: Environment variable defaults
- **WHEN** environment variables `DRAGNCARDS_HTTP_URL`, `DRAGNCARDS_WS_URL`, `DEV_USER_EMAIL`, and `DEV_USER_PASSWORD` are not set
- **THEN** tests SHALL default to `http://localhost:4000`, `ws://localhost:4000/socket`, `dev_user@example.com`, and `password` respectively

#### Scenario: marvel-lcg environment variable defaults
- **WHEN** environment variables `MARVEL_LCG_BASE_URL` and `MARVEL_LCG_PASSWORD` are not set
- **THEN** the marvel-lcg integration tests SHALL default to `http://localhost:4006` and `password`, matching the compose default published port and the documented local password

#### Scenario: Plugin registry configuration
- **WHEN** `MC_PLUGIN_ID` and `MC_PLUGIN_VERSION` environment variables are not set
- **THEN** the integration test plugin registry SHALL default to plugin ID `1` and version `3` for `marvel-champions`

#### Scenario: A platform migration is proven on a throwaway database
- **WHEN** a migration adding a platform column is exercised by the history-service or eval-service integration suite
- **THEN** the suite SHALL create a `<service>_test_<uuid>` database, run every migration against it in order, assert the column and the widened constraints, and drop the database in teardown

### Requirement: Test suites are independent of the environment's provider configuration
Every test suite SHALL produce the same result regardless of which LLM providers the developer running it has enabled or holds API keys for. No test SHALL fail, and no test SHALL silently stop asserting, because a provider is disabled, keyless or absent.

Test harnesses SHALL NOT inherit service configuration from the ambient environment. Each suite SHALL neutralise the environment variables its settings model can read and SHALL set the values its assertions depend on explicitly, keeping only a documented allowlist of variables the suite genuinely needs to reach an external dependency such as PostgreSQL or Valkey.

A test that genuinely requires a live, keyed provider SHALL skip with a reason naming that requirement rather than passing vacuously or failing.

#### Scenario: Narrowed provider list keeps the suite green
- **WHEN** the unit and integration suites are run with the service's provider list narrowed to a single provider, or with a provider such as OpenAI removed, whether exported in the shell or supplied through the service `.env` that the test runner passes to the suite
- **THEN** every test SHALL pass or skip with a stated reason, and the result SHALL match the result at the repository default configuration

#### Scenario: Provider identity is not asserted as a vendor literal
- **WHEN** a test assigns a model configuration to a session, or asserts on the set of listed providers
- **THEN** it SHALL use the provider set its own harness pins, or the application's configured providers, rather than a hardcoded vendor identifier that a deployment may have disabled

#### Scenario: Harness independence is itself covered
- **WHEN** a provider list is present in the environment while the suite builds its application under test
- **THEN** the application SHALL be configured with the provider set the harness pins, and a test SHALL assert this so the independence cannot regress unnoticed

#### Scenario: Settings defaults are asserted against a clean environment
- **WHEN** a test asserts on a configuration default
- **THEN** the corresponding environment variable SHALL have been neutralised by the suite, so the assertion describes the declared default rather than the machine the suite runs on

#### Scenario: Disabled-provider rejection stays exercised
- **WHEN** the suite asserts that assigning a supported-but-disabled provider is rejected
- **THEN** the harness SHALL guarantee that at least one supported provider is disabled, and the test SHALL assert that precondition rather than skipping when it does not hold

#### Scenario: Frontend configuration defaults do not leak in
- **WHEN** the dashboard test suite runs in a shell that exports the stack's service URLs or session defaults such as the default provider and model
- **THEN** the suite SHALL clear those variables before each test, and a guard SHALL fail if the configuration module starts reading a variable the suite does not clear

### Requirement: Frontend tests wait for the render they assert on
A frontend test SHALL assert on content that appears as the result of an
asynchronous chain only through a query that waits for it — `findBy*`, or a
synchronous query inside `waitFor` — and SHALL NOT query for it synchronously
after awaiting some earlier step of that chain.

Awaiting that a mocked API function was *called* SHALL NOT be treated as
evidence that the render caused by its result has committed. A call is the first
step of the handler that makes it; the state updates that follow it are separated
from it by every remaining `await` in that handler plus a React commit.

The suite SHALL NOT rely on React Testing Library's post-`waitFor` drain to
deliver those commits. That drain is a single `setTimeout(…, 0)`, clamped to one
millisecond — a fixed grace period rather than a wait for the condition. Whether a
handler's promise chain fits inside it depends on how busy the machine is, which
makes any assertion resting on it a function of the machine rather than of the
behaviour under test.

A synchronous query MAY follow an awaited one when it reads state committed in the
same render as the awaited content — state set together with it in one handler is
batched into one commit and is therefore already on screen.

#### Scenario: Content rendered after an awaited API call is awaited
- **WHEN** a test submits a prompt and asserts on the streaming banner that
  appears once the submission's follow-up request has resolved and streaming has
  started
- **THEN** the banner SHALL be asserted through an awaited query, so the
  assertion waits for the render that produces it rather than for the submission
  call that precedes it

#### Scenario: The result does not depend on the machine's load
- **WHEN** the dashboard suite is run repeatedly while other test suites are
  running on the same machine, so that promise chains and timers are stretched
- **THEN** every test SHALL produce the same result as it does on an idle
  machine, and no test SHALL fail because a render had not committed when it was
  queried

#### Scenario: State committed alongside awaited content stays synchronous
- **WHEN** a test has awaited content whose render also set other state in the
  same handler
- **THEN** that other state MAY be asserted synchronously, because React commits
  the batched updates together and the awaited query has already waited for that
  commit

### Requirement: Integration coverage for the live marvel-lcg play loop
Integration tests SHALL prove the whole marvel-lcg loop against a live instance of the platform, in one test, in the order the platform actually requires: authenticate and obtain the version cookie, create a game, connect the render-frame WebSocket and announce the client, receive a frame naming the seat as pending, read the enumerated legal options for that seat, submit one of them by its identifier, and observe the game state advance past that prompt.

The test SHALL assert the platform's own transport facts rather than assume them, because each one has already produced a confusing failure: game creation alone advances nothing until a client is attached; a response can carry HTML with HTTP 200 instead of JSON when a required cookie is absent, which surfaces as a WebSocket handshake failure rather than an authentication error; and move submission always answers `200` with an empty body, so success is observable only in the state that follows.

The submitted option SHALL be chosen from the list the engine returned, keyed by its identifier, so the test proves the enumerated-option contract rather than a hardcoded move. Option names are not unique within a prompt, so a test that selects by name is not selecting deterministically and SHALL NOT do so.

The test SHALL bound its own waiting and SHALL fail loudly on a prompt that does not clear, rather than retrying indefinitely: the platform re-asks invalid input forever with no cap, so an unbounded test is a self-inflicted denial of service against the instance the rest of the suite shares.

#### Scenario: The whole loop runs end to end
- **WHEN** the integration test creates a game against a live marvel-lcg instance, connects the render-frame socket, waits for its seat to be asked, reads the enumerated options, and submits one by identifier
- **THEN** the platform SHALL report a subsequent state in which that prompt is no longer pending, and the test SHALL assert on that observed advance rather than on the submission's response body

#### Scenario: Creating a game without connecting advances nothing
- **WHEN** the integration test creates a game and reads the world before connecting the socket
- **THEN** the state SHALL still be empty, and the test SHALL assert that emptiness so the ordering constraint is covered rather than assumed

#### Scenario: An HTML response with a 200 status is treated as a failure
- **WHEN** a platform request answers with `text/html` and status `200` because a required cookie was absent
- **THEN** the test SHALL fail naming the unexpected content type, rather than parsing it or reporting a downstream socket handshake error

#### Scenario: An option is selected by identifier, not by name
- **WHEN** the enumerated options for a prompt contain two options sharing the same name
- **THEN** the test SHALL select one by its identifier and SHALL assert that the two were distinguishable, so a name-keyed selection cannot pass

#### Scenario: A prompt that will not clear fails the test
- **WHEN** a submission leaves the same prompt pending for the test's bounded number of attempts
- **THEN** the test SHALL fail naming the stuck prompt and SHALL stop submitting, rather than retrying until the engine's own unbounded retry loop saturates the instance

### Requirement: Integration coverage proves the marvel-lcg debug endpoint is unreachable
Integration tests SHALL prove that marvel-lcg's `GET /debug` endpoint — unauthenticated arbitrary code execution on a platform that binds all interfaces — is not reachable through any first-party surface. This SHALL be a test, not a review item, because it is the highest-severity item in this work and inspection is what allowed the platform to ship it in the first place.

The test SHALL attempt the debug path through the dashboard's service proxy and through the Game Service's own routes, and SHALL assert that each surface refuses it. The test SHALL also assert that no first-party code composes a URL carrying that path or the platform's cheat-mode query parameters.

The test SHALL NOT depend on the platform itself refusing the request, because it does not: with no password set the platform serves it to anyone who can reach the port. What is asserted is that our surfaces offer no route to it.

#### Scenario: The debug path is refused by every first-party surface
- **WHEN** the integration test requests the platform's debug path through the dashboard service proxy and through the Game Service
- **THEN** each surface SHALL refuse the request, and no request SHALL reach the platform

#### Scenario: No first-party code composes a debug or cheat URL
- **WHEN** the test exercises the platform URL construction used by the Game Service driver and by the dashboard viewer resolver over every supported seat and mode
- **THEN** no produced URL SHALL contain the debug path or a cheat-mode query parameter
