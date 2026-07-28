## ADDED Requirements

### Requirement: Agent session deletion
The system SHALL expose an HTTP endpoint to permanently delete an agent session, removing the session together with every record stored under it: its model configuration, enabled skills, MCP assignments, player configurations, jobs, transcript events, job outputs, and compaction records.

Deletion SHALL return no content on success and SHALL report an unknown session as not found, including on a repeated deletion of the same session.

Deletion SHALL terminate before it deletes: cancellation SHALL be requested for any queued or running job in the session before its rows are removed, so an executing worker observes the cancellation rather than discovering that its records have disappeared.

Deletion SHALL be scoped to the session: global skill and MCP registries, and any other session, SHALL be unaffected. Jobs belonging to other sessions that reference a deleted job SHALL have that reference cleared rather than left dangling.

Every dependent row SHALL be removed explicitly rather than relying on database-level cascade behaviour, so that no transcript, compaction, or configuration row can be orphaned on a backend that does not enforce the declared foreign keys.

Terminating a session SHALL remain distinct from deleting it: termination ends the session while preserving its history, and only deletion removes that history.

#### Scenario: Delete a session and its history
- **WHEN** a client deletes an existing agent session
- **THEN** the system SHALL remove the session with its model configuration, enabled skills, MCP assignments, player configurations, jobs, transcript events, outputs, and compaction records, and SHALL return a no-content response
- **AND** subsequent requests for that session or for its jobs SHALL report them as not found

#### Scenario: Delete a session that is still executing
- **WHEN** a client deletes a session that has a queued or running job
- **THEN** the system SHALL request cancellation of that job before removing the session, and SHALL still complete the deletion

#### Scenario: Delete an unknown session
- **WHEN** a client deletes a session identifier that does not exist, or deletes the same session twice
- **THEN** the system SHALL respond that the session was not found

#### Scenario: Deletion leaves other sessions intact
- **WHEN** a client deletes one session while other sessions exist
- **THEN** the other sessions and their jobs SHALL remain retrievable, the global skill and MCP registries SHALL be unchanged, and any job in another session that referenced a deleted job SHALL have that reference cleared
