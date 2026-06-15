## ADDED Requirements

### Requirement: Action helper endpoints have descriptive summaries
The Game Service SHALL provide descriptive summaries for all explicit action handler endpoints to improve MCP tool discoverability.

#### Scenario: Action helper endpoints have summaries
- **WHEN** an MCP client queries available tools
- **THEN** each action tool SHALL include a descriptive summary explaining its purpose and when to use it

#### Scenario: Summaries warn about preferred alternatives
- **WHEN** an agent views tool descriptions in their MCP client
- **THEN** low-level tools SHALL include warnings about better-typed alternatives (e.g., `set_card_property` warns to use `flip_card` instead)

#### Scenario: Drawing to hand limit has clear guidance
- **WHEN** an agent needs to draw cards up to hand limit
- **THEN** the `mulligan_draw_hand` tool description SHALL clarify it is the preferred tool for this use case over `draw_card`