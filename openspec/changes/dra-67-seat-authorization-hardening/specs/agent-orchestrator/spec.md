## ADDED Requirements

### Requirement: Player-seat identity requires roster registration

A session SHALL be treated as a player seat only when its server-created player identity metadata names an orchestrated parent and the parent's persisted player configuration for that player names the same child session. Public session create and update requests SHALL NOT be able to set or overwrite the server-owned player identity metadata fields. A missing or mismatched roster registration SHALL resolve to no seat identity and SHALL not receive seat-scoped authorization.

#### Scenario: Forged public metadata does not grant seat identity

- **WHEN** a public session request includes `player_id`, `player_display_name`, or `orchestrator_session_id` in its metadata
- **THEN** those server-owned identity fields SHALL be removed before the session is persisted
- **AND** the session SHALL not acquire player-seat identity from that request

#### Scenario: Registered seat session resolves

- **WHEN** a child session's server-created identity names an orchestrated parent and the parent's player configuration maps that player to the same child session
- **THEN** seat resolution SHALL return that player identity

#### Scenario: Unregistered seat session is rejected

- **WHEN** a child session's metadata names an orchestrated parent and player but the parent's persisted roster does not map that player to the child session
- **THEN** seat resolution SHALL return no identity
- **AND** seat-scoped authorization SHALL not be granted

### Requirement: Persistent seat claims are race-safe

When an orchestrated seat has no persistent agent session, assigning a child session to that seat SHALL be an atomic conditional database update that succeeds only while the seat remains unclaimed. A losing claim SHALL leave the existing owner unchanged, and later prompts SHALL continue reusing the stored owner.

#### Scenario: First persistent claim wins

- **WHEN** a child session is assigned to an unclaimed configured seat
- **THEN** the conditional claim SHALL succeed and persist that child session id

#### Scenario: Existing persistent claim cannot be replaced

- **WHEN** a second child session attempts to claim a seat that already has an agent session id
- **THEN** the claim SHALL report failure
- **AND** the stored agent session id SHALL remain the original owner
