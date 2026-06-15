## MODIFIED Requirements

### Requirement: Game action execution
The Game Service SHALL provide endpoints and MCP tools to execute game actions within a session.

#### Scenario: Execute a card movement action with instance_id parameter
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to move a card from one group to another (e.g., play a card from hand to the play area)
- **THEN** the Game Service SHALL accept `instance_id` as the parameter name for the card identifier, consistent with the `instanceId` naming in the game state JSON

#### Scenario: Execute card property action with instance_id parameter
- **WHEN** a client sends `POST /games/{id}/actions` or invokes the `execute_action` MCP tool with an action to set a card property
- **THEN** the Game Service SHALL accept `instance_id` as the parameter name for the card identifier, consistent with the `instanceId` naming in the game state JSON