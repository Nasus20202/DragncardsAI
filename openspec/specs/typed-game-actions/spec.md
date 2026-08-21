# typed-game-actions Spec

(Generated from delta: typed-game-actions)

## Purpose

This capability defines the explicitly written, validated game-action helpers exposed by
game-service. The typed action vocabulary and its raw DragnLang fallback describe the
DragnCards move surface; a rules-enforcing platform uses its own enumerated-option surface.

## Requirements

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

That helper SHALL be available only for a session whose platform is `dragncards`, because a DragnLang action list is meaningful only to a platform that interprets DragnLang. Invoked for a session on another platform it SHALL be refused with an error naming that session's platform, and the action list SHALL NOT be forwarded, reinterpreted, or mapped onto that platform's own move surface.

#### Scenario: Raw action helper executes a custom action list
- **WHEN** a caller invokes the raw action helper with an action list payload for a DragnCards session
- **THEN** the action SHALL be executed and return the standard success acknowledgment

#### Scenario: A raw DragnLang list is refused for another platform
- **WHEN** a caller invokes the raw action helper for a session whose platform is not `dragncards`
- **THEN** the Game Service SHALL refuse the request with an error naming that session's platform
- **AND** SHALL NOT forward the action list to that platform

### Requirement: The typed action vocabulary is DragnCards-scoped

The typed action helpers SHALL be understood as describing the DragnCards move surface only, and so
SHALL their request and response models, the action catalog they are derived from, and the raw
DragnLang fallback.
Every one of them composes a DragnLang action list for a platform that accepts whatever the client
pushes, and neither the vocabulary nor that assumption transfers to a platform whose engine
adjudicates the rules.

A typed helper, the generic action endpoint, and the raw fallback SHALL be reachable only for a
session whose platform is `dragncards`. Invoked for a session on any other platform, each SHALL be
refused with an error naming that session's platform and the move surface it does offer, and SHALL NOT
translate, approximate, or partially apply the request. A session action catalog SHALL advertise the
typed helpers only for a DragnCards session.

A platform whose engine enumerates the legal move set SHALL be driven through the
`enumerated-game-options` contract instead, and the typed action vocabulary SHALL NOT be widened to
cover it. Conversely, the enumerated-option surface SHALL NOT replace the typed helpers for
DragnCards, whose engine enumerates nothing.

#### Scenario: A typed helper on a non-DragnCards session is refused
- **WHEN** a client invokes a typed action helper for a session whose platform is not `dragncards`
- **THEN** the request SHALL be refused with an error naming that session's platform and its enumerated-option surface
- **AND** no action SHALL be sent to that platform

#### Scenario: The action catalog advertises typed helpers only for DragnCards
- **WHEN** a client reads the session action catalog for a session whose platform is not `dragncards`
- **THEN** the catalog SHALL NOT list the typed action helpers or the raw DragnLang fallback

#### Scenario: DragnCards sessions keep the full typed surface
- **WHEN** a client invokes any typed action helper for a session whose platform is `dragncards`
- **THEN** the helper SHALL behave exactly as it did before the platform distinction existed
- **AND** its request model, response model, and emitted DragnLang SHALL be unchanged
