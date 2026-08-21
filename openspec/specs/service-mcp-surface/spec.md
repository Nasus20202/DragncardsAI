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

Four classes of route SHALL be excluded:

- liveness and readiness probes, for every service;
- routes whose response does not terminate promptly — server-sent event streams, and streaming exports that return an entire recorded game;
- operations that destroy data irreversibly or mutate deployment-global state shared by every session;
- routes that reach an external game platform's debug, cheat, arbitrary-command, or replay-injection surface. This class differs from the other three: such a route SHALL NOT exist at all rather than merely being kept off the MCP surface, because the capability it forwards is arbitrary code execution on a platform our services are the only thing able to reach.

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

#### Scenario: A platform's arbitrary-command surface is not reachable at all
- **WHEN** `game-service`'s routes and MCP tools are inspected
- **THEN** no route or tool SHALL forward to a game platform's debug, cheat, arbitrary-command, or replay-injection endpoint
- **AND** the absence SHALL hold over HTTP as well, unlike the other exclusion classes which leave the HTTP endpoint intact

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
- **THEN** the documentation SHALL state which check commands are safe and why, including that   the integration fixtures create and drop a throwaway database rather than using the running services' data

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
- **THEN** validation SHALL pass, because   the root flag forbids undeclared tool arguments, not the contents of a property the endpoint declares as open

### Requirement: Enumerated legal options are tools on game-service's MCP surface
`game-service` SHALL expose the enumerated-option surface as MCP tools: one tool that lists the legal options currently offered to a seat, and one tool that submits a chosen option for that seat. Both SHALL be produced by the same derivation as every other tool — a route with an explicit, readable, verb-first `operation_id` — so the tool is the endpoint it came from and no hand-written tool layer is introduced beside it.

The listing tool SHALL identify each option by the identifier the submitting tool takes, and SHALL carry enough context for a model to choose between two options that differ only by that identifier: the option's name, its legal targets resolved to card names and types, its target-count range, and its payment options. Option names are not unique within a prompt, so a surface that presents names alone is not a surface a model can choose from.

The submitting tool SHALL take the chosen option's identifier together with the targets and resource payments it requires, and SHALL report the outcome the service concluded from the state that followed the submission. The platform's own answer is always an empty success, so a tool result derived from it would tell a model nothing.

Both tools SHALL be scoped to a session and a seat, so an agent can only submit for the seat it holds.

#### Scenario: The option tools are present and named readably
- **WHEN** a client lists `game-service`'s MCP tools for a session on a platform that enumerates legal moves
- **THEN** the surface SHALL include a readable verb-first tool for listing that seat's legal options and one for submitting a chosen option, each named by its route's explicit `operation_id`

#### Scenario: Two options sharing a name are distinguishable
- **WHEN** the listing tool returns a prompt whose options include two entries with the same name
- **THEN** each entry SHALL carry its own identifier and its targets resolved to card names and types, so a model can state which of the two it means

#### Scenario: A submission reports a concluded outcome
- **WHEN** a model submits a chosen option through the tool and the platform answers with an empty success
- **THEN** the tool result SHALL report the outcome the service concluded from the state that followed, including the case where the prompt did not clear, rather than reporting success because the platform returned no error

### Requirement: A game platform's routes are exposed or excluded by an explicit decision
`game-service` SHALL treat every platform-specific route it adds as a decision about its MCP surface. The surface derives every tool from a route's `operation_id`, and the exclusion list in the service's own source is the only thing standing between a route and a tool, so a platform-specific route is a tool by default — and the default is the wrong direction for a platform whose own surface includes arbitrary command execution.

Every marvel-lcg route the service adds SHALL be either exposed deliberately or excluded deliberately, and the exclusion policy SHALL be extended in the same change that adds the route. A route left unconsidered SHALL be treated as a defect in that change, not discovered later from the tool list.

The service SHALL expose no route that reaches a platform's debug, cheat, arbitrary-command, replay-injection, or third-party card-script surface — over MCP or over HTTP. These are not exclusions that leave an HTTP endpoint for a developer, as the general exclusion policy allows: the route SHALL NOT exist, because marvel-lcg's debug command path is unauthenticated arbitrary code execution and the service is the only thing on the internal network that can reach it.

The exclusion policy SHALL continue to be verified against the tool names the service's real application produces, so an exclusion pattern that matches nothing is distinguishable from one that works, and so the pinned tool set fails when a platform route is added without a decision.

#### Scenario: A platform route is decided in the change that adds it
- **WHEN** a marvel-lcg route is added to `game-service`
- **THEN** the change SHALL either give it an explicit `operation_id` as an intended tool or add it to the exclusion policy, and the pinned tool-set test SHALL be updated in the same change

#### Scenario: No debug or cheat route exists to exclude
- **WHEN** `game-service`'s routes are inspected
- **THEN** none SHALL forward to a platform's debug, cheat, arbitrary-command, replay-injection, or custom card-script surface, over MCP or over HTTP

#### Scenario: The pinned tool set catches an undecided route
- **WHEN** a platform route is added without extending the exclusion policy or intending a tool
- **THEN** the test that pins the built surface SHALL fail, naming the tool that appeared

### Requirement: Existing DragnCards tool names and schemas are unchanged by platform support
Adding a second platform SHALL NOT change any existing DragnCards tool. Every tool name currently present on `game-service`'s MCP surface SHALL remain present and identically named, and each SHALL keep the input schema it has today, including its enumerated group and layout vocabularies and its root refusal of additional properties.

This holds even though the vocabularies those schemas contain become lazily and per-platform resolved. A diff in a DragnCards tool's name or schema is a regression in this work, not an update to it, because the orchestrator's seat and turn guards, the evaluation action taxonomy, the skill corpus and the browser smoke test all name those tools as literals.

The tests that pin these surfaces SHALL stay green without being edited. An edit to a pinned expectation SHALL be treated as evidence the refactor changed a public surface it was required to preserve.

#### Scenario: The DragnCards tool set is byte-for-byte the same
- **WHEN** the MCP tool names and input schemas of `game-service` are compared before and after platform support is added, for a deployment with the Marvel Champions plugin content present
- **THEN** every existing tool SHALL be present under the same name with the same input schema

#### Scenario: Pinned surface tests are not edited to pass
- **WHEN** the tests pinning the MCP exclusion set, the strict request bodies, and the capability surface are run against the refactored service
- **THEN** they SHALL pass unedited, and any change required in those expectations SHALL be treated as a regression to fix in the service rather than in the test

#### Scenario: The surface builds with no platform content on disk
- **WHEN** `game-service` builds its application and its MCP surface with no plugin JSON or card data present for any platform
- **THEN** the surface SHALL build, and the tools whose schemas depend on a platform's vocabulary SHALL still declare their enumerations for a platform whose content is present rather than failing the build for every platform
