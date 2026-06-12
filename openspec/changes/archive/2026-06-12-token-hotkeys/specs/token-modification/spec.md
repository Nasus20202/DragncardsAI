## ADDED Requirements

### Requirement: Modify tokens action available
The Game Service SHALL provide a `modify_tokens` typed action for adding or removing tokens from cards.

#### Scenario: Add tokens to a card
- **WHEN** a client sends `POST /games/{session_id}/actions/modify_tokens` with `{"instance_id": "card-123", "token_type": "threat", "amount": 2}`
- **THEN** the Game Service SHALL translate it to `["INCREASE_VAL", "/cardById/card-123/tokens/threat", 2]`

#### Scenario: Remove tokens from a card
- **WHEN** a client sends `POST /games/{session_id}/actions/modify_tokens` with `{"instance_id": "card-456", "token_type": "damage", "amount": -1}`
- **THEN** the Game Service SHALL translate it to `["INCREASE_VAL", "/cardById/card-456/tokens/damage", -1]`

### Requirement: Token type validation
The Game Service SHALL validate that `token_type` is one of the known Marvel Champions token types.

#### Scenario: Reject unknown token type
- **WHEN** a caller sends `modify_tokens` with `token_type` not in the enum
- **THEN** the Game Service SHALL reject the request with a validation error

### Requirement: MCP tool exposure
The Game Service SHALL expose the `modify_tokens` action as an MCP tool named `modify_tokens`.

#### Scenario: MCP tool available
- **WHEN** an MCP client lists available tools
- **THEN** `modify_tokens` SHALL be in the tool list with correct schema for `instance_id`, `token_type`, and `amount`