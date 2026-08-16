## ADDED Requirements

### Requirement: MCP tool schemas refuse arguments the endpoint does not take

Each service's MCP tool schema SHALL declare at its root that additional
properties are not permitted, so that a client applying the schema refuses a tool
call carrying an argument the endpoint does not define at inference time, before
the call is built.

This exists because the strict request bodies the endpoints declare do not by
themselves protect a tool call: FastMCP builds a tool's input schema by
flattening the request body's properties alongside the path parameters into a
fresh object and never copies the body model's `additionalProperties` flag up to
that object's root, and an argument the route's parameter map does not know is
then dropped by FastMCP's request director with a log warning and reported to the
model as success. The flag at the flattened root is what a strict client — Claude
among them, the direction FastMCP's own defaults lean on — validates a generated
call against.

The flag SHALL be enforced at the tool schema's root only. A property the
endpoint declares as an open mapping — session `metadata`, `gateway_options`,
`provider_options` — SHALL continue to accept arbitrary contents at its own
level, exactly as under `extra='forbid'` on the HTTP layer.

The flag SHALL NOT be relied on to make the server refuse an already-built call.
The strictness operates at inference time in the client that applies the schema;
a request the director does receive with an unknown argument is still handled as
before.

`game-service` predates the shared library and keeps an equivalent copy of the
MCP bootstrap; the requirement SHALL hold for that copy as well, so the two
implementations stay in step.

#### Scenario: Every reachable tool forbids additional properties at the root
- **WHEN** a client lists any service's MCP tools
- **THEN** each tool's input schema root SHALL declare `additionalProperties: false`

#### Scenario: A hallucinated tool argument is refused before the call is built
- **WHEN** a strict client validates a tool call carrying an argument the endpoint does not define, such as `create_session` with `allowed_subagants`
- **THEN** validation SHALL fail naming the argument, so the call is refused rather than reaching the request director and returning success with the argument dropped

#### Scenario: A valid call still validates
- **WHEN** a strict client validates a tool call carrying only arguments the endpoint defines
- **THEN** validation SHALL pass, so the flag does not reject legitimate calls

#### Scenario: Declared open mappings keep accepting arbitrary contents
- **WHEN** a strict client validates a tool call whose `metadata` or `provider_options` argument carries keys the service has never seen
- **THEN** validation SHALL pass, because the root flag forbids undeclared tool arguments, not the contents of a property the endpoint declares as open
