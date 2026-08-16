## ADDED Requirements

### Requirement: The capability-negotiation endpoint is not an MCP tool

Each service SHALL keep its `GET /capabilities` route out of its MCP surface,
because the endpoint describes the server's own state — the same class as the
liveness and readiness probes — and an agent gains nothing from a tool that
tells it about the server it is already talking to. The route SHALL remain fully
functional over HTTP, since the client that needs the answer asks over HTTP
before it sends anything.

The exclusion SHALL be enacted by the same shared mechanism that excludes the
probes, and game-service SHALL declare it in its own exclusion list, so a
service cannot silently expose the endpoint as a tool by forgetting to opt out.

#### Scenario: Capabilities is absent from every tool list

- **WHEN** a client lists any of the four services' MCP tools
- **THEN** the `capabilities` tool SHALL be absent, while `GET /capabilities`
  over HTTP SHALL keep working

#### Scenario: The exclusion is verified against the built surface

- **WHEN** a service's exclusion policy is tested
- **THEN** the test SHALL assert on the tool names produced by the service's
  real application, and SHALL confirm that `capabilities` is absent
