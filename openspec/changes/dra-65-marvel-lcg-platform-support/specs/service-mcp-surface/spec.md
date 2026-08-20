# Service MCP Surface

## ADDED Requirements

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

## MODIFIED Requirements

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
