## ADDED Requirements

### Requirement: Per-player evaluation display
The dashboard SHALL display evaluation results per player at each level (move, round, game),
labelling each verdict with the player it pertains to, and SHALL present a per-player game
scorecard that shows each player's move/round/game scores side by side so players can be
compared. Move/round/game verdicts SHALL be visually distinguishable by both their level and
their player.

#### Scenario: Verdicts show their player
- **WHEN** the dashboard renders an evaluation verdict in the transcript
- **THEN** it SHALL show which player the verdict pertains to (alongside its scope/level), and
  per-player round/game verdicts SHALL be distinguishable from move verdicts

#### Scenario: Per-player game scorecard
- **WHEN** a game has per-player evaluations
- **THEN** the dashboard SHALL present a scorecard comparing each player's move/round/game scores

### Requirement: Request a cascade evaluation
The dashboard SHALL let the user request a higher-level (round or whole-game) evaluation that
auto-grades the components beneath it, and the persistent evaluations queue SHALL reflect the
resulting fan-out of sub-evaluations as they progress.

#### Scenario: Whole-game cascade from the UI
- **WHEN** the user requests a whole-game evaluation
- **THEN** the dashboard SHALL submit the cascade and the queue SHALL show the moves, rounds, and
  game sub-evaluations progressing to completion
