## ADDED Requirements

### Requirement: DragnCards player turns start in the player phase

When an orchestrated DragnCards round is ready to dispatch its first player seat and the neutral game state is still outside the player phase, the orchestrator SHALL advance the platform through its required transition and SHALL confirm the resulting state is the player phase before prompting any seat. It SHALL report the round from the confirmed neutral `playRound` value and SHALL NOT ask a player agent to repair or undo a transition that belongs to the round loop.

#### Scenario: Setup transitions before the first seat is prompted

- **WHEN** an orchestrated DragnCards game is ready for its first seat but the neutral state reports setup or passive phase
- **THEN** the orchestrator SHALL advance the game into the player phase
- **AND** it SHALL confirm the neutral state reports `phase=player` before prompting the first seat
- **AND** the first seat SHALL receive the confirmed neutral play-round value

#### Scenario: A failed phase transition stops seat dispatch

- **WHEN** the DragnCards transition does not produce a confirmed player phase
- **THEN** the orchestrator SHALL report the transition failure
- **AND** it SHALL NOT prompt a player seat or ask a seat to undo an unstarted turn