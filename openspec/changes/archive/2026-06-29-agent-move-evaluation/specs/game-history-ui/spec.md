## MODIFIED Requirements

### Requirement: Game history timeline view
The dashboard SHALL provide a view that lists a game's history as an ordered timeline of events and snapshots retrieved from the history-service.

#### Scenario: Display ordered timeline for a game
- **WHEN** a user opens the history view for a `game_id`
- **THEN** the dashboard SHALL display the game's events ordered by ascending `seq`, distinguishing `agent` move/decision events, `game-service` game-state events, and `evaluator` evaluation events

#### Scenario: Surface snapshots on the timeline
- **WHEN** the history view renders a game's timeline
- **THEN** the dashboard SHALL indicate which points in the timeline have stored snapshots available as restore points

#### Scenario: Show decision context for an agent move
- **WHEN** a user selects an `agent` move event in the timeline
- **THEN** the dashboard SHALL display the captured intended action and reasoning/context for that move

#### Scenario: Show game status for a state event
- **WHEN** a user selects a `game-service` state event in the timeline
- **THEN** the dashboard SHALL display the resulting game status for that event

#### Scenario: Empty history
- **WHEN** a user opens the history view for a `game_id` with no stored events
- **THEN** the dashboard SHALL display an empty-state message rather than an error

## ADDED Requirements

### Requirement: Surface evaluator events and scores on the timeline
The dashboard SHALL surface `evaluator` events on the game history timeline, visually distinct from agent and game-service events, anchored to the move or round they grade, and SHALL show the verdict detail when an evaluator event is selected.

#### Scenario: Evaluator event anchored to the graded move or round
- **WHEN** the history view renders a game's timeline containing an `evaluator` event
- **THEN** the dashboard SHALL display that evaluator event anchored to the move (`target_seq`) or round (`round_span`) it grades, visually distinct from agent and game-service events

#### Scenario: Show verdict detail for an evaluator event
- **WHEN** a user selects an `evaluator` event in the timeline
- **THEN** the dashboard SHALL display the per-criterion scores, the overall score, the rationale, and any flags from the verdict payload

#### Scenario: Timeline without evaluator events
- **WHEN** a game has no `evaluator` events yet
- **THEN** the dashboard SHALL render the timeline normally without an error and without claiming evaluations exist

### Requirement: Request evaluation of selected moves or rounds
The dashboard SHALL provide a control for the user to select which targets of a game to evaluate — one or more moves, one or more rounds, a range, or the whole game — and to submit that evaluation request to the eval-service, then surface the request's progress and resulting verdicts on the timeline.

#### Scenario: Select targets and request evaluation
- **WHEN** a user selects one or more moves/rounds (or the whole game) on the history view and confirms an evaluation request
- **THEN** the dashboard SHALL submit an evaluation request for exactly those targets and SHALL show that the request was accepted

#### Scenario: Surface evaluation progress and results
- **WHEN** an evaluation request the user submitted is in progress or completes
- **THEN** the dashboard SHALL reflect the per-target status (pending/completed/failed) and render the resulting verdicts on the timeline as they appear

#### Scenario: No evaluation without a user request
- **WHEN** a user views a game's history without requesting any evaluation
- **THEN** the dashboard SHALL NOT trigger any evaluation automatically
