## ADDED Requirements

### Requirement: Marvel Champions typed action models
The Game Service SHALL provide Marvel Champions-specific typed action models for common gameplay patterns.

#### Scenario: Exhaust card action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `exhaust_card`
- **THEN** the Game Service SHALL translate it to the appropriate DragnLang `EXHAUST_CARD` operation

#### Scenario: Ready card action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `ready_card`
- **THEN** the Game Service SHALL translate it to the appropriate DragnLang `READY_CARD` operation

#### Scenario: Flip card action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `flip_card`
- **THEN** the Game Service SHALL translate it to a conditional SET operation that cycles through card sides

#### Scenario: Deal encounter card action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `deal_encounter`
- **THEN** the Game Service SHALL translate it to the appropriate DragnLang `DEAL_ENCOUNTER_CARD` operation

#### Scenario: Draw boost card action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `draw_boost`
- **THEN** the Game Service SHALL translate it to the appropriate DragnLang for drawing boost cards

#### Scenario: Shuffle into deck action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `shuffle_into_deck`
- **THEN** the Game Service SHALL move the card to its deck and shuffle that deck

#### Scenario: Zero tokens action available
- **WHEN** a client sends `POST /games/{id}/actions` with type `zero_tokens`
- **THEN** the Game Service SHALL set the card's tokens to an empty object