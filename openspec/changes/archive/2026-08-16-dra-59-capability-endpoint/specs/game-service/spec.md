## ADDED Requirements

### Requirement: Capability endpoint

The game-service SHALL expose `GET /capabilities`, returning a JSON document
with the service name, the service's version string, and the list of features
the server supports, so a client can detect version skew before it sends
anything.

The feature list SHALL be derived from the service's own OpenAPI document — one
`verb:path` entry per documented route, for example `post:/games` or
`get:/games/{session_id}/state` — rather than from a hand-maintained list, so a
route added later is advertised without anyone remembering to add it and a route
removed stops being advertised. The derivation SHALL be asserted structurally by
a test that reads the app's own OpenAPI document and fails if the advertised
feature list does not cover every documented route exactly once.

The endpoint SHALL be excluded from the service's MCP surface, because it
describes the server's own state like the liveness probe, and SHALL remain fully
functional over HTTP.

A server built before this requirement SHALL answer `GET /capabilities` with
`404`, and a client SHALL treat that response as the signal that the server
predates the negotiation.

#### Scenario: A client learns what the server supports

- **WHEN** a client sends `GET /capabilities` to the game-service
- **THEN** the service SHALL respond `200` with the service name, the version
  string, and a feature list containing one `verb:path` entry per documented
  route

#### Scenario: A new route is advertised without a list edit

- **WHEN** a route is added to the game-service and the service's OpenAPI
  document is read
- **THEN** the added route SHALL appear in the `/capabilities` feature list,
  because the list is derived from the document rather than maintained by hand

#### Scenario: The advertised features match the route table

- **WHEN** the service's `/capabilities` response is compared against its own
  OpenAPI document
- **THEN** every documented route SHALL appear exactly once in the feature list

#### Scenario: Capabilities is not an MCP tool

- **WHEN** a client lists the game-service's MCP tools
- **THEN** the `capabilities` tool SHALL be absent, while `GET /capabilities`
  over HTTP SHALL keep working

#### Scenario: A server that predates the endpoint is detectable

- **WHEN** a client sends `GET /capabilities` to a server built before this
  requirement
- **THEN** the server SHALL answer `404`, and the client SHALL treat that
  response as the signal that the server predates the negotiation
