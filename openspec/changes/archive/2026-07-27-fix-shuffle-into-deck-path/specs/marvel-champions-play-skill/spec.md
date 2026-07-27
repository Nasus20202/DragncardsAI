## MODIFIED Requirements

### Requirement: Skill teaches the action result contract and recovery
The skill SHALL state that an action response always reports `success: true` and that the only failure signal is a non-null `error` string, and SHALL instruct the agent to read `error` after every mutating call. It SHALL state that the previous-step tool moves only the step marker and performs no undo, and SHALL describe correcting a mistake by issuing inverse actions.

#### Scenario: Error field is checked after every action
- **WHEN** the skill describes executing any mutating tool
- **THEN** it SHALL treat a non-null `error` as a failed action regardless of the `success` value

#### Scenario: Previous-step is not an undo
- **WHEN** the skill describes recovering from a mistake
- **THEN** it SHALL state that the previous-step tool does not revert card moves, token changes, or exhaustion
- **AND** it SHALL give inverse-action sequences for the reversible mistakes

#### Scenario: Returning a card to a deck distinguishes shuffling from placing
- **WHEN** the skill describes returning a card to its deck
- **THEN** it SHALL direct the agent to the shuffle-into-deck tool for effects that say to shuffle the card in
- **AND** it SHALL direct the agent to the move tool with a top-of-deck destination for effects that say to place the card on top without shuffling
- **AND** it SHALL state that the shuffle-into-deck tool derives its destination from the card's own deck group and cannot be redirected
