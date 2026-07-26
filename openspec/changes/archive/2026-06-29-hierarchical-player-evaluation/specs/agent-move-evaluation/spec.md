## ADDED Requirements

### Requirement: Hierarchical evaluation levels with dependency
The eval-service SHALL support three evaluation levels with a dependency relationship —
move → round → game — where a round-level evaluation depends on the evaluations of its
constituent moves and a game-level evaluation depends on the evaluations of its constituent
rounds. A higher-level evaluation SHALL NOT be produced unless every component beneath it has
been evaluated.

#### Scenario: Round depends on its moves
- **WHEN** a round-level evaluation is produced
- **THEN** every agent move within that round SHALL have an evaluation that the round evaluation
  is grounded in

#### Scenario: Game depends on its rounds
- **WHEN** a game-level evaluation is produced
- **THEN** every round within that game SHALL have an evaluation that the game evaluation is
  grounded in

### Requirement: Auto-grading cascade
The eval-service SHALL, when a round-level or game-level evaluation is requested and some
required lower-level components are not yet evaluated, first evaluate the missing components
(moves, then rounds) and then evaluate the requested level, so a single request fans out across
the entire subtree it requires. Already-evaluated components SHALL be reused unless a forced
re-evaluation is requested (config-aware idempotency).

#### Scenario: Game request cascades to moves and rounds
- **WHEN** a game-level evaluation is requested for a game whose moves and rounds are not all
  evaluated
- **THEN** the eval-service SHALL evaluate the ungraded moves, then the rounds, then the game,
  reusing any components already evaluated with the same judge configuration

### Requirement: Judge-with-child-context roll-up
A round-level or game-level score SHALL be produced by the judge grading the span holistically
with the child evaluations (their scores and rationales) provided as context, rather than as a
purely numeric aggregate of child scores.

#### Scenario: Round score considers its move verdicts
- **WHEN** the eval-service produces a round-level evaluation
- **THEN** the judge SHALL be given the round's move evaluations as context and SHALL produce a
  holistic round score and rationale (not a mechanical average)

### Requirement: Per-player attribution and results
The eval-service SHALL attribute each agent move to the active player derived from the game
state at that move, and SHALL produce a separate round-level and game-level result for each
player who acted within the span — scoring that player's moves (round) and that player's rounds
(game). Move-level evaluations are attributed to their acting player. Each evaluation result
SHALL carry the `player` it pertains to. A single-player game has one player.

#### Scenario: Separate per-player results for a multi-player span
- **WHEN** a round or game spanning the actions of more than one player is evaluated
- **THEN** the eval-service SHALL produce a distinct evaluation result for each player who acted,
  each scoring only that player's contributions, each carrying that player's id

#### Scenario: Move attributed to its acting player
- **WHEN** a move is evaluated
- **THEN** the evaluation SHALL carry the id of the player who was active for that move, derived
  from the game state
