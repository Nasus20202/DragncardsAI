## MODIFIED Requirements

### Requirement: Persistent seat claims are race-safe

When an orchestrated seat has no persistent agent session, assigning a child session to that seat SHALL be an atomic conditional database update that succeeds only while the seat remains unclaimed. A losing claim SHALL leave the existing owner unchanged, SHALL not enqueue or schedule the losing child, and SHALL clean up the losing child session. The prompt operation SHALL return an error that allows the coordinator to retry against the persisted owner, and later prompts SHALL continue reusing the stored owner.

#### Scenario: First persistent claim wins

- **WHEN** a child session is assigned to an unclaimed configured seat
- **THEN** the conditional claim SHALL succeed and persist that child session id
- **AND** the child job SHALL be eligible for scheduling

#### Scenario: Existing persistent claim cannot be replaced

- **WHEN** a second child session attempts to claim a seat that already has an agent session id
- **THEN** the claim SHALL report failure
- **AND** the stored agent session id SHALL remain the original owner

#### Scenario: A losing first claim cannot run

- **WHEN** two first prompts race for the same unclaimed orchestrated seat
- **THEN** exactly one child session SHALL become the persisted seat owner
- **AND** the losing child session SHALL be terminated before a child job is enqueued or scheduled
- **AND** the losing prompt operation SHALL return an error result
