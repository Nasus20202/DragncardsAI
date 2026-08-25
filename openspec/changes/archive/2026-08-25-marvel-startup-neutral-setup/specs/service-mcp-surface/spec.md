## ADDED Requirements

### Requirement: Setup discovery is a backend-agnostic generated MCP tool

The game-service MCP surface SHALL expose `list_game_setup_catalog`, generated from the
`GET /games/setup-catalog` route. The tool SHALL accept the same optional platform selector as
HTTP, default to `dragncards` when omitted, and return the route's typed catalog including
`platform` and `move_surface`. It SHALL not require a platform-specific MCP server, registry entry,
or hand-written tool implementation.

#### Scenario: One tool discovers either backend

- **WHEN** an MCP client invokes `list_game_setup_catalog` for DragnCards or marvel-lcg
- **THEN** the same game-service tool SHALL return the selected platform's typed setup catalog
- **AND** the response SHALL identify the platform and move surface

#### Scenario: The generated tool and HTTP route agree

- **WHEN** a client invokes setup discovery through HTTP and MCP with the same platform
- **THEN** both calls SHALL execute the same handler
- **AND** both responses SHALL contain the same scenario/deck ids and capability metadata

#### Scenario: Unknown tool arguments are refused

- **WHEN** an MCP client invokes `list_game_setup_catalog` with an argument other than the declared
  platform selector
- **THEN** the strict tool schema SHALL refuse the argument before request dispatch

### Requirement: Generated create-game schemas carry typed platform setup

The generated `create_game` tool schema SHALL expose the optional discriminated platform setup
specification in the outer `setup` field, including Marvel's `scenario_id` and ordered neutral
`{seat, hero_deck_id}` entries. It SHALL not expose an untyped `plugin_info` escape hatch. The tool response SHALL include
`platform`, `move_surface`, and the resolved setup selection.

#### Scenario: MCP can create the requested Marvel roster

- **WHEN** a client discovers Marvel ids and invokes `create_game` with the typed scenario and
  ordered `hero_decks` selections inside `setup`
- **THEN** the generated tool SHALL pass those values to the same create handler as HTTP
- **AND** the response SHALL identify the selected platform, move surface, and ordered setup

#### Scenario: The tool does not silently accept legacy Marvel fields

- **WHEN** an MCP client supplies an undeclared Marvel setup field or an untyped plugin mapping
- **THEN** the strict schema SHALL reject it
- **AND** no engine creation request SHALL be made

### Requirement: Marvel option tool arguments match the neutral route contract

The generated `list_game_options` tool SHALL take `session_id` and `player_n`, with `player_n`
defaulting to `player1` where the route does. The generated `choose_game_option` tool SHALL take
`player_n` in its strict request body together with the option id, targets, resources, explicit
decline, and required `prompt_id` and `prompt_version` fields. Neither tool SHALL declare or
silently discard a `player` argument.

#### Scenario: The option tools use `player_n`

- **WHEN** an MCP client lists the game-service tools
- **THEN** the option tool schemas SHALL name the seat argument `player_n`
- **AND** a valid call with `player_n: player2` SHALL reach the corresponding seat

#### Scenario: The stale `player` argument is rejected

- **WHEN** an MCP client calls either Marvel option tool with `player` instead of `player_n`
- **THEN** schema validation SHALL refuse the call or the strict request SHALL return a named
  validation error
- **AND** the service SHALL not default the call to the wrong seat

## MODIFIED Requirements

### Requirement: MCP tools are derived from the service's own OpenAPI schema

Each service SHALL derive its MCP tools from its own FastAPI OpenAPI schema. The neutral setup
catalog and typed create-game fields SHALL therefore be represented in the same OpenAPI schemas
used by HTTP, and every tool call SHALL execute the route handler rather than a separate MCP
implementation. Platform-specific move tools remain capability-specific, but the common discovery
and lifecycle tools SHALL not require backend-specific MCP knowledge.

#### Scenario: Adding neutral setup discovery adds one generated tool

- **WHEN** the game-service publishes the setup catalog route
- **THEN** `list_game_setup_catalog` SHALL appear from its explicit operation id
- **AND** no hand-written duplicate setup tool SHALL exist

#### Scenario: A new endpoint becomes a tool without further work

- **WHEN** a route is added to a service and is not excluded by its service exclusion policy
- **THEN** the corresponding MCP tool SHALL appear with the route's own parameter and response
  schema without a separate tool definition

#### Scenario: An endpoint's behaviour is not reimplemented for MCP

- **WHEN** a generated MCP tool is invoked
- **THEN** it SHALL execute that endpoint's own handler
- **AND** the MCP result and HTTP response SHALL not disagree
