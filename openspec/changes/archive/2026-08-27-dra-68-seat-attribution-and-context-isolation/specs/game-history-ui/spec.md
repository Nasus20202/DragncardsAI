## ADDED Requirements

### Requirement: Attribute agent moves by player

The dashboard history transcript SHALL display the recorded non-empty `player` value on each attributed `agent` move as a distinct player label in that move's always-visible summary. The transcript SHALL omit the player label when the move has no usable player value.

#### Scenario: Attributed move identifies its seat

- **WHEN** the timeline contains an `agent` move whose payload has `player` set to `player1`
- **THEN** the move summary SHALL visibly include the label `player1` alongside the agent label

#### Scenario: Legacy move remains readable without attribution

- **WHEN** the timeline contains an `agent` move whose payload has no non-empty `player` value
- **THEN** the move summary SHALL remain visible without rendering an empty or fabricated player label
