## MODIFIED Requirements

### Requirement: Request evaluation of selected moves or rounds
The dashboard SHALL provide a control for the user to select which targets of a game to evaluate — one or more moves, one or more rounds, a range, or the whole game — and to submit that evaluation request to the eval-service, then surface the request's progress and resulting verdicts on the timeline.

Choosing what to evaluate SHALL be ONE question, not two independent ones. The control SHALL offer a single mutually-exclusive choice of what is being graded — moves, rounds, or the whole game — and each choice SHALL own whatever further input it needs. Selecting a round SHALL mean selecting a round: the user SHALL pick rounds from a list of the game's actual rounds and SHALL NOT be required to select a move, a sequence, or a range in order to grade a round. The round list SHALL come from the eval-service's own round detection rather than being re-derived in the dashboard, so a round the user can pick is a round the service can grade, and each round SHALL be labelled with its round of play together with its sequence span and how many moves it contains.

The whole-game choice SHALL require no further input. The moves choice SHALL be the only one that consults the transcript selection or a sequence range. Combinations that carry no meaning SHALL NOT be expressible.

#### Scenario: Select targets and request evaluation
- **WHEN** a user selects one or more moves/rounds (or the whole game) on the history view and confirms an evaluation request
- **THEN** the dashboard SHALL submit an evaluation request for exactly those targets and SHALL show that the request was accepted

#### Scenario: Grading a round needs no move selected
- **WHEN** the user chooses to evaluate rounds with no transcript event selected, picks one or more rounds from the offered list, and submits
- **THEN** the dashboard SHALL submit a round-scope request naming those rounds, SHALL NOT require a move or sequence to be chosen, and SHALL NOT report a missing selection

#### Scenario: Rounds are offered with a readable label
- **WHEN** the user chooses to evaluate rounds for a game whose first recorded round reports a DragnCards round number of 0
- **THEN** that round SHALL be offered as round 1, alongside its sequence span and its number of moves, and submitting it SHALL name the same number the service listed rather than a converted one

#### Scenario: Round list comes from the service
- **WHEN** the dashboard offers the rounds of a game
- **THEN** the offered rounds SHALL be those the eval-service reports for that game

#### Scenario: What-to-evaluate is a single choice
- **WHEN** the user picks the whole game
- **THEN** no further target input SHALL be requested, and the transcript selection and sequence range SHALL have no bearing on what is submitted

#### Scenario: Surface evaluation progress and results
- **WHEN** an evaluation request the user submitted is in progress or completes
- **THEN** the dashboard SHALL reflect the per-target status (pending/completed/failed) and render the resulting verdicts on the timeline as they appear

#### Scenario: No evaluation without a user request
- **WHEN** a user views a game's history without requesting any evaluation
- **THEN** the dashboard SHALL NOT trigger any evaluation automatically

### Requirement: Per-player evaluation display
The dashboard SHALL display evaluation results per player at each level (move, round, game),
labelling each verdict with the player it pertains to, and SHALL present a per-player game
scorecard that shows each player's move/round/game scores side by side so players can be
compared. Move/round/game verdicts SHALL be visually distinguishable by both their level and
their player.

The scorecard SHALL NOT average verdicts produced by different evaluator versions into one
figure, because a change to what the judge is shown or asked moves the scale. It SHALL aggregate
the newest evaluator version present for the game and SHALL disclose how many older-version
verdicts it excluded, so an out-of-date verdict is visible rather than silently folded in.

#### Scenario: Verdicts show their player
- **WHEN** the dashboard renders an evaluation verdict in the transcript
- **THEN** it SHALL show which player the verdict pertains to (alongside its scope/level), and
  per-player round/game verdicts SHALL be distinguishable from move verdicts

#### Scenario: Per-player game scorecard
- **WHEN** a game has per-player evaluations
- **THEN** the dashboard SHALL present a scorecard comparing each player's move/round/game scores

#### Scenario: Scorecard excludes stale evaluator versions
- **WHEN** a game holds verdicts from an older evaluator version alongside verdicts from the newest one
- **THEN** the scorecard SHALL average only the newest version's verdicts and SHALL state how many older-version verdicts it left out

## ADDED Requirements

### Requirement: Hero UI controls in the evaluate panel
Every interactive control in the dashboard's evaluate panel SHALL be a Hero UI component or one of the dashboard's shared field wrappers built from them, and SHALL NOT be a hand-rolled native form element. Specifically the what-to-evaluate choice SHALL be a radio group, the round picker SHALL be a checkbox group, the sequence range bounds SHALL be labelled text fields of the same shared kind the judge panel uses, re-evaluate SHALL be a toggle switch row rather than a native checkbox, and the error and confirmation states SHALL be Hero UI alerts.

Adopting these components SHALL NOT change the panel's behavior or remove its automation surface: submission SHALL stay disabled while a request is in flight or no game is selected, and each control SHALL expose an accessible name and a stable test id.

#### Scenario: Controls are Hero UI components
- **WHEN** the user opens the evaluate panel
- **THEN** each control SHALL be a Hero UI component or a shared field wrapper built from one, and the panel SHALL NOT render a bare native radio, number, or checkbox input

#### Scenario: Behaviour is unchanged by the components
- **WHEN** a game is not selected, or an evaluation request is being submitted
- **THEN** the panel's controls and its submit action SHALL be disabled, exactly as before
