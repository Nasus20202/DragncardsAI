## ADDED Requirements

### Requirement: Simplified Marvel Champions state output
The Game Service SHALL provide a simplified representation of Marvel Champions game state that includes only essential information for LLM decision-making.

#### Scenario: Simplified state filters to essential fields
- **WHEN** a client requests `GET /games/{id}/state?format=simplified` for a Marvel Champions session
- **THEN** the response SHALL include only `roundNumber`, `mode`, `villainHitPoints`, `players` (with hitPoints and handSize), and `zones` (with visible cards including `id`, `instanceId`, `name`, `currentSide`, `exhausted`, `tokens`)

#### Scenario: Simplified state excludes attachment hierarchy
- **WHEN** a card is an attachment tucked under another card
- **THEN** the simplified state SHALL NOT include that attachment as a separate entry in its zone's card list

#### Scenario: Simplified state omits null player aliases
- **WHEN** a player has a null alias in the raw state
- **THEN** that player SHALL be omitted from the simplified state's players object