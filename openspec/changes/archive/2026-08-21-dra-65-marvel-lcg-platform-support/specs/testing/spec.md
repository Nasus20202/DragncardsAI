# Testing

## MODIFIED Requirements

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

## ADDED Requirements

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
