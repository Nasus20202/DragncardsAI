## MODIFIED Requirements

### Requirement: Per-player attribution and results
The eval-service SHALL attribute each agent move to the active player, and SHALL produce a
separate round-level and game-level result for each player who acted within the span — scoring
that player's moves (round) and that player's rounds (game). Move-level evaluations are
attributed to their acting player. Each evaluation result SHALL carry the `player` it pertains
to. A single-player game has one player.

Attribution SHALL prefer an acting-player id explicitly recorded on the move over any inferred
value. When a move carries an explicitly recorded player, that value SHALL be used even if the
player count cannot be derived from recorded game state. Only when no explicit value is present
SHALL the eval-service fall back to deriving the active player from the game state at that move.

#### Scenario: Separate per-player results for a multi-player span
- **WHEN** a round or game spanning the actions of more than one player is evaluated
- **THEN** the eval-service SHALL produce a distinct evaluation result for each player who acted,
  each scoring only that player's contributions, each carrying that player's id

#### Scenario: Move attributed to its acting player
- **WHEN** a move is evaluated
- **THEN** the evaluation SHALL carry the id of the player who was active for that move

#### Scenario: Explicitly recorded player wins over inference
- **WHEN** a move was recorded with an explicit acting-player id and the game state would imply a
  different player
- **THEN** the eval-service SHALL attribute the move to the explicitly recorded player

#### Scenario: Explicit player without derivable state
- **WHEN** a move was recorded with an explicit acting-player id and the recorded state does not
  reveal how many players are in the game
- **THEN** the eval-service SHALL attribute the move to the explicitly recorded player rather than
  defaulting to the single-player id

#### Scenario: Legacy games keep heuristic attribution
- **WHEN** a game recorded without explicit acting-player ids is evaluated
- **THEN** the eval-service SHALL attribute its moves from the game state exactly as before
