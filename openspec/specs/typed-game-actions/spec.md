# typed-game-actions Spec

(Generated from delta: typed-game-actions)

## ADDED Requirements

### Requirement: Typed action helpers are exposed
The Game Service SHALL expose a typed helper function for each action type returned by the session action catalog, with an explicit request model and response model per action, implemented as explicitly written functions (not dynamically generated).

#### Scenario: Discoverable typed helper coverage
- **WHEN** a client inspects the game action helpers in the game service action module
- **THEN** there SHALL be a distinct helper for every action type exposed by `get_session_actions`

### Requirement: Typed helpers validate action payloads
The Game Service SHALL validate typed helper requests against the corresponding action schema, including required fields and default values.

#### Scenario: Reject invalid typed request
- **WHEN** a caller invokes a typed helper with missing required fields
- **THEN** the Game Service SHALL reject the request with a validation error that identifies the missing fields

### Requirement: Typed helpers preserve action execution semantics
The Game Service SHALL execute typed helper actions through the same underlying action execution path as the generic `execute_action` interface and return the same success acknowledgment shape.

#### Scenario: Typed helper returns success acknowledgment
- **WHEN** a caller executes a typed action helper with a valid payload
- **THEN** the response SHALL include the session identifier and a success indicator matching the generic action execution response

### Requirement: Raw action fallback remains available
The Game Service SHALL continue to support a raw action helper that accepts an arbitrary DragnLang action list for cases where no typed helper applies.

#### Scenario: Raw action helper executes a custom action list
- **WHEN** a caller invokes the raw action helper with an action list payload
- **THEN** the action SHALL be executed and return the standard success acknowledgment
