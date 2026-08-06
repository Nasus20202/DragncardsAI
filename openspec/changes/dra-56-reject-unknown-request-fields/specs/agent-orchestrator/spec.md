## ADDED Requirements

### Requirement: Unknown request-body fields are refused

The agent-orchestrator SHALL reject a request whose body carries a field the
receiving model does not define, responding with HTTP `422` and naming the
offending field, rather than accepting the request and discarding the field.

This SHALL hold for **every** request body the service accepts, not for a chosen
subset. A request model that does not enforce it is a defect regardless of which
endpoint it serves, because a discarded field is indistinguishable from an applied
one to the client that sent it, and several of these bodies write security-shaped
configuration — the subagent allowlist, a persona's tool allowlist, a seat's
persona.

The service SHALL have no endpoint that accepts an unmodelled request body, so
that the rule has no endpoint it cannot reach.

Strictness applies to a model's own keys. A field declared as an open mapping —
session `metadata`, `gateway_options`, `provider_options` — SHALL continue to
accept any contents, because an open dictionary is its declared shape and not an
absence of validation.

Refusing an unknown field SHALL NOT change any endpoint's existing validation of
values it does know. In particular, registering a skill without a name SHALL
remain a `400`, because that is a check on a value rather than on the body's
shape.

This requirement SHALL NOT be read as protecting a client from an
agent-orchestrator older than the field it is sending. The check is performed by
the server, so it can only refuse what that server knows to be unknown; an
orchestrator predating a field accepts and discards it as before, and detecting
that remains the client's responsibility.

#### Scenario: An unknown field on a session update is refused
- **WHEN** a client sends `PATCH /sessions/{session_id}` with a body containing a field the agent-orchestrator does not define
- **THEN** the agent-orchestrator SHALL respond `422` and name that field
- **AND** SHALL NOT apply any part of the request

#### Scenario: An unknown field on session creation is refused
- **WHEN** a client sends `POST /sessions` with a body containing a field the agent-orchestrator does not define
- **THEN** the agent-orchestrator SHALL respond `422` and name that field
- **AND** SHALL NOT create a session

#### Scenario: Every request body the service exposes is strict
- **WHEN** the agent-orchestrator's OpenAPI document is read
- **THEN** every schema referenced by a request body SHALL declare that additional properties are not permitted

#### Scenario: Open mappings still accept arbitrary contents
- **WHEN** a client sends a session update whose `metadata` object carries keys the agent-orchestrator has never seen
- **THEN** the agent-orchestrator SHALL accept the request and store the metadata unchanged

#### Scenario: A known-field validation failure keeps its existing status
- **WHEN** a client registers a skill with a body that omits `name`
- **THEN** the agent-orchestrator SHALL respond `400` as before, not `422`
