## ADDED Requirements

### Requirement: Room semantics are owned by one room Module
The Game Service SHALL concentrate room semantics behind one room Module whose Interface is used by HTTP adapters, MCP adapters, and session-pool orchestration.

That room Module SHALL own state refresh, stale-state recovery, action execution, room control operations, alert buffering, GUI update buffering, and room-side error handling.

Phoenix protocol details such as event names, refs, payload construction, and raw send/wait behavior SHALL live behind a Phoenix Adapter at the Seam and SHALL NOT be required knowledge for callers using room behavior.

#### Scenario: HTTP and MCP adapters share room semantics
- **WHEN** a caller uses HTTP or MCP to observe state, execute an action, or invoke room control for the same session
- **THEN** both adapters SHALL delegate through the same room Module Interface
- **AND** SHALL observe the same state-freshness, recovery, and room-side error semantics

#### Scenario: Phoenix protocol knowledge is hidden behind an Adapter
- **WHEN** room behavior requires Phoenix join refs, message refs, event names, or wire payloads
- **THEN** that knowledge SHALL be owned by a Phoenix Adapter behind the room Module Seam
- **AND** SHALL NOT be duplicated in HTTP adapters, MCP adapters, or session-pool callers

### Requirement: Generic game action definitions have one source of truth
The Game Service SHALL define generic game action typing, translation, and catalog metadata from one concentrated action Module so that generic action behavior is described once and reused across the system.

#### Scenario: Global and session action catalogs share generic definitions
- **WHEN** a client requests `GET /actions` and `GET /games/{session_id}/actions`
- **THEN** the generic action schemas and descriptions in both responses SHALL be derived from the same action definition source

#### Scenario: Generic action execution reuses shared translation logic
- **WHEN** the Game Service executes a generic action that also appears in the action catalog, including player-count changes
- **THEN** the Game Service SHALL route that action through the shared action translation Module
- **AND** SHALL NOT require a second translation Implementation for the same action semantics
