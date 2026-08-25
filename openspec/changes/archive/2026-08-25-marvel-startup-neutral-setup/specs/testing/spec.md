## ADDED Requirements

### Requirement: Startup and setup selection are tested through the public surfaces

The test suite SHALL verify that ordinary Compose startup includes the marvel-lcg engine and
initializer without a profile, that setup discovery is available through HTTP and generated MCP,
and that typed creation uses the caller's selected scenario and ordered hero decks. Tests SHALL
assert explicit `platform` and `move_surface` metadata, the typed resolved setup OpenAPI schema,
and SHALL cover both supported move surfaces without requiring them to be identical.

#### Scenario: Compose configuration starts both backends normally

- **WHEN** the Compose configuration is rendered without profiles
- **THEN** the Marvel engine and initializer SHALL be present and the readiness graph SHALL include
  them
- **AND** no test SHALL need to add a Marvel profile to exercise ordinary startup

#### Scenario: Neutral catalog and MCP tool agree

- **WHEN** a test requests Marvel setup through HTTP and `list_game_setup_catalog` through MCP
- **THEN** both responses SHALL expose the same selected ids, `platform`, and `move_surface`
- **AND** neither path SHALL create a game

#### Scenario: Requested heroes are not replaced

- **WHEN** an integration test creates a Marvel game with two explicitly selected hero-deck ids in
  seat order
- **THEN** the returned metadata and state SHALL identify those heroes in that order
- **AND** the test SHALL fail if the first catalog entries or a fixed hero are used instead

### Requirement: Singleton engine constraints are tested explicitly

Marvel integration tests SHALL cover one active lease per configured engine endpoint, renewal during
delayed creation/connection, exact-token release on pre-registration failure, refusal of a second
create, release on teardown, lease loss, and refusal of unsupported attachment. They SHALL clean up
the owning session and lease even when setup or move assertions fail. Unit coverage SHALL also
verify that `close_room` is rejected without closing the Marvel transport or releasing its lease.

#### Scenario: Competing Marvel creation is rejected

- **WHEN** one test session owns the Marvel engine and a second test client attempts creation
- **THEN** the second request SHALL fail with the singleton conflict before engine creation
- **AND** the first session SHALL remain usable

#### Scenario: Marvel attachment is not guessed

- **WHEN** an integration test invokes attach for a service-generated Marvel slug
- **THEN** the service SHALL return the documented unsupported-attachment error
- **AND** it SHALL not connect to an arbitrary active engine game

#### Scenario: An unavailable Marvel backend is readiness-oriented

- **WHEN** setup discovery cannot reach the Marvel backend or its initialization prerequisite
- **THEN** the API SHALL return `503` with a retry-oriented response
- **AND** it SHALL not report an empty valid catalog

### Requirement: Skill and generated option schemas are contract-tested

Tests SHALL compare the Marvel harness reference's option call examples with the generated tool
schemas and SHALL require `player_n` for both list and choose calls, plus `prompt_id` and
`prompt_version` for choices. The stale `player` argument SHALL be rejected, and a valid call SHALL
reach the requested neutral seat.

#### Scenario: Skill and schema use the same seat argument

- **WHEN** the skill contract and generated MCP schemas are inspected
- **THEN** both SHALL use `player_n`
- **AND** both SHALL describe the same option id, target, resource, and decline semantics

#### Scenario: A stale Marvel option call is not silently repaired

- **WHEN** a client sends `player` instead of `player_n`
- **THEN** validation SHALL fail with a named argument error
- **AND** the service SHALL not execute or redirect the call
