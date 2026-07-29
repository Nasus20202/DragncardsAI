# service-mcp-surface Specification

## Purpose

Make every first-party backend service drivable by an agent as tools rather than as
documentation, so that the whole loop this system exists to run — create a game, start a
player agent, read the actions it took, read the resulting board, request an evaluation,
read the verdict — can be exercised end to end without a human reading source to guess at
request shapes.

The loop spans four services, and only `game-service` was ever reachable this way. An agent
debugging a run had tool schemas for the board and nothing for the sessions that drove it,
the events that recorded it, or the verdicts that graded it, so three quarters of the flow
had to be inferred from code and curl. That asymmetry, not any missing endpoint, is what
this capability removes.

Two properties make the surface trustworthy enough to keep. **Tools are generated from each
service's own OpenAPI schema**, so a tool is the endpoint it came from and cannot drift from
it; there is deliberately no hand-written tool layer to maintain as a second implementation
of the API. And **each service declares what it keeps out**, because these services
authenticate nobody: an operation that never completes (an SSE stream), that would buffer a
whole recorded game into a caller's context, that destroys the only durable record of what
an agent did, or that mutates deployment-global state shared with sessions the caller does
not own, is not offered to a model as a tool. Exclusion is an MCP-surface decision only —
the HTTP endpoint is untouched, so nothing here constrains the dashboard or a developer with
`curl`. Per-session cleanup stays exposed on purpose, so excluding the dangerous cases never
costs an agent the ability to undo its own work.

## Requirements
### Requirement: Every first-party backend service exposes an MCP surface
The system SHALL expose `game-service`, `agent-orchestrator`, `history-service` and `eval-service` as MCP servers over the streamable-HTTP transport at the path `/mcp` on each service's own HTTP port, and SHALL register all four in the repository's MCP client configuration so an assistant working in the repository can reach them without further setup.

A service reachable only over HTTP SHALL be regarded as not satisfying this requirement. An agent debugging the system has no tool schemas for such a service and must infer request shapes from source, which is the condition this capability exists to remove.

#### Scenario: Each service serves the MCP transport at a stable path
- **WHEN** any of the four backend services is running
- **THEN** it SHALL serve the MCP streamable-HTTP transport at `/mcp` on its own port, and SHALL respond to a correctly negotiated MCP `initialize` request with a session identifier

#### Scenario: The repository configuration lists every surface
- **WHEN** an assistant loads the repository's MCP client configuration
- **THEN** that configuration SHALL name one server per backend service, addressing each at its `/mcp` endpoint

#### Scenario: A bare GET is not treated as a successful read
- **WHEN** a caller issues a plain `GET` to a service's `/mcp` endpoint without MCP content negotiation
- **THEN** the service SHALL reject the request rather than return a document, because the endpoint is a protocol transport and not a page

### Requirement: MCP tools are derived from the service's own OpenAPI schema
Each service SHALL derive its MCP tools from its own FastAPI OpenAPI schema, so that every tool corresponds to exactly one HTTP endpoint and carries that endpoint's request and response schema. The system SHALL NOT define an MCP tool that is not generated from an endpoint.

A hand-written tool layer would be a second implementation of the API, free to diverge from the first, and the existing rule that MCP tools and HTTP endpoints behave consistently would depend on review rather than on construction.

#### Scenario: A new endpoint becomes a tool without further work
- **WHEN** a route is added to a service and is not excluded by that service's exclusion policy
- **THEN** the corresponding MCP tool SHALL appear in that service's surface with the route's own parameter and response schema, with no separate tool definition written

#### Scenario: An endpoint's behaviour is not reimplemented for MCP
- **WHEN** an MCP tool generated from an endpoint is invoked
- **THEN** it SHALL execute that endpoint's own handler, so the MCP result and the HTTP response cannot disagree

### Requirement: Every route carries an explicit operation identifier
Each service SHALL declare an explicit, readable, verb-first `operation_id` on every HTTP route, because the tool name an MCP client presents is that operation identifier.

A framework-generated identifier such as `submit_prompt_sessions__session_id__prompts_post` is shortened by the MCP layer into a lossy and collision-prone name, and the tool list is the only surface by which an agent discovers what a service can do.

#### Scenario: Tool names are readable and unique within a service
- **WHEN** a client lists a service's MCP tools
- **THEN** each tool name SHALL be a readable verb-first identifier such as `create_session`, `list_game_events` or `create_evaluation`, and SHALL be unique within that service

#### Scenario: Adding a route without an operation identifier is a defect
- **WHEN** a route is added without an explicit `operation_id`
- **THEN** the change SHALL be treated as incomplete, because the resulting tool is named by the framework's generated identifier rather than by the author

### Requirement: Each service declares what it keeps out of its MCP surface
Each service SHALL declare, in its own source, the routes excluded from its MCP surface, and that declaration SHALL be treated as a security boundary rather than a matter of tidiness. These services authenticate no caller, so every tool present in a surface is an operation an LLM can perform on a running deployment without further check.

Exclusion SHALL remove a route from the MCP surface only. The HTTP endpoint SHALL remain fully functional, so the operation stays available to a developer who invokes it deliberately and to the dashboard.

Three classes of route SHALL be excluded:

- liveness and readiness probes, for every service;
- routes whose response does not terminate promptly — server-sent event streams, and streaming exports that return an entire recorded game;
- operations that destroy data irreversibly or mutate deployment-global state shared by every session.

Operations scoped to a single session or a single object that the caller created SHALL remain exposed, so that an agent can always undo its own work.

#### Scenario: Probes are never tools
- **WHEN** a client lists any service's MCP tools
- **THEN** the health and readiness endpoints SHALL be absent, and a service SHALL NOT be able to opt back into exposing them

#### Scenario: Streaming responses are not tools
- **WHEN** a service offers a server-sent event endpoint or a streaming whole-game export
- **THEN** that route SHALL be absent from the MCP surface, and the service's documentation SHALL name the paged read to use instead

#### Scenario: Irreversible destruction is not a tool
- **WHEN** an operation would irreversibly destroy recorded history, write fabricated events into the ordered event store, or bulk-delete records the caller did not create
- **THEN** that route SHALL be absent from the MCP surface while remaining available over HTTP

#### Scenario: Deployment-global registries are readable but not writable over MCP
- **WHEN** a client lists the MCP tools of a service holding a deployment-global registry of skills, MCP servers or personas
- **THEN** the read operations SHALL be present and the create, update and delete operations SHALL be absent, because an entry changed there changes what every session in the deployment resolves

#### Scenario: An agent can clean up after itself
- **WHEN** an agent has created a game, an orchestrator session or an evaluation request through the MCP surface
- **THEN** the tools needed to delete or terminate exactly those objects SHALL be present in the surface

#### Scenario: Exclusions are verified against the built surface
- **WHEN** a service's exclusion policy is tested
- **THEN** the test SHALL assert on the tool names produced by the service's real application, not on the contents of the exclusion list, because an exclusion pattern that matches nothing is indistinguishable from one that works

### Requirement: The MCP surface bootstrap is shared by the services that can use it
The system SHALL provide one implementation of building and mounting a service's MCP surface, in the internal `dragncards-common` library, and the Python services that depend on that library SHALL use it rather than each carrying its own copy. A service's own module SHALL declare only its name and its exclusion policy.

`game-service` is a documented exception: it predates the shared library, does not depend on it, and installs from its own lockfile, so it keeps an equivalent copy of the bootstrap. That exception SHALL be recorded in the agent instructions so the duplication is not read as an accident and a third copy is not added.

#### Scenario: A service wires its surface by declaring its exclusions
- **WHEN** a service that depends on the shared library exposes an MCP surface
- **THEN** it SHALL do so by calling the shared bootstrap with its service name and its exclusion list, and SHALL NOT reimplement the schema derivation, the transport mount or the lifespan composition

#### Scenario: Mounting the transport does not displace the service's own startup
- **WHEN** the MCP transport is mounted on a service's application
- **THEN** the application's existing lifespan SHALL still run, composed with the MCP session manager's lifespan, so both start and shut down together

#### Scenario: The surface is mounted in the entrypoint, not the application factory
- **WHEN** a test or another caller builds a service's application through its factory
- **THEN** no MCP server SHALL be built and no MCP session manager SHALL be started, and the service's entrypoint SHALL be what mounts the surface

### Requirement: The end-to-end debugging loop is documented for an agent
The repository SHALL document, in the agent instruction file an assistant reads first, the complete loop by which an agent verifies a change against a running system: create a game, start a player agent on it, analyse the agent's recorded actions, read the live board state, request an evaluation, and read the verdict.

For each step the documentation SHALL name the concrete tools and the required fields, and SHALL state what to check to know the step succeeded. It SHALL also record the behaviours of the system that its source does not make evident and that otherwise have to be rediscovered.

#### Scenario: Each step names its tools and its success check
- **WHEN** an agent reads the documented loop
- **THEN** each of the six steps SHALL name the tools to call, the fields those tools require, and an observable condition confirming the step worked

#### Scenario: Prerequisites that block the loop are stated before the steps
- **WHEN** an agent begins the loop
- **THEN** the documentation SHALL have already stated the conditions that silently prevent it: that a new git worktree does not populate submodules and how that failure presents; that a running stack may serve older images than the working tree, and how to detect it; that the evaluation step requires a configured judge model and provider key, and that a service reporting `degraded` readiness will fail every evaluation target instead of refusing the request; and that the specification validation command has one known pre-existing failure

#### Scenario: Non-obvious system behaviour is recorded rather than rediscovered
- **WHEN** the documentation covers starting a player agent and reading what it did
- **THEN** it SHALL state that no operation binds an orchestrator session to a game and that the agent learns its game and its seat only from the prompt text, and that a job stopped by the tool-round limit emits a completion event while ending in a non-successful status

#### Scenario: The documentation says which checks are safe against a live deployment
- **WHEN** an agent is deciding whether to run a check against a running system it does not own
- **THEN** the documentation SHALL state which check commands are safe and why, including that the integration fixtures create and drop a throwaway database rather than using the running services' data

