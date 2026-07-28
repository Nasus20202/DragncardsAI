## MODIFIED Requirements

### Requirement: Bounded judge input
The judge input SHALL be reduced by PROJECTION before any character bound is applied: a recorded raw game state SHALL be projected to the information a judge needs to rule on a play — round, phase, per-seat vitals, and the visible cards per zone with the identifiers the move's arguments reference — rather than being character-clipped as recorded. Hidden information SHALL remain hidden: face-down cards and undrawn deck contents SHALL be reported as a count, never by name. A recorded state whose shape the projection does not recognise SHALL be sent as recorded rather than dropped. A configurable character bound SHALL remain as a backstop, and any truncation SHALL be marked in the input and logged.

A per-move judge input SHALL include a CONFIGURABLE WINDOW of the agent's neighbouring moves rather than the whole recorded history, bounded independently for preceding and following moves, so that a move belonging to a multi-step play is not judged in isolation while the input does not grow with the length of the game. The following-moves portion SHALL be labelled as completion context rather than an outcome to grade, and it SHALL be possible to configure it away entirely.

A round-level or game-level judge input SHALL carry the recorded game state for the end of its span, falling back to the nearest recorded state at or before the closing sequence when the closing event itself carries none, so a roll-up is never graded with no board.

#### Scenario: Large game does not overflow a small model
- **WHEN** a whole-game (or large) evaluation would exceed the configured input bound
- **THEN** the input is truncated to fit and the truncation is recorded, rather than sending an oversized prompt

#### Scenario: Recorded internal engine data never reaches the judge
- **WHEN** a per-move evaluation is assembled from a recorded raw game state that contains an internal engine change log, plugin configuration, layout data and full card definitions alongside the board
- **THEN** the judge input SHALL contain the board — the round, the phase, each seat's vitals, and the visible cards in each zone — and SHALL NOT contain the internal change log, plugin configuration or layout data, and SHALL be a small fraction of the recorded state's size

#### Scenario: Hidden information stays hidden
- **WHEN** the projected state includes a zone holding undrawn deck cards or face-down cards
- **THEN** those cards SHALL be reported only as a count under a hidden marker, and their names SHALL NOT appear anywhere in the judge input

#### Scenario: Unrecognised state shape is preserved
- **WHEN** a recorded state is not in the raw shape the projection understands
- **THEN** it SHALL be serialised as recorded and bounded by the configured character limit, so no content is silently discarded

#### Scenario: Neighbouring moves are windowed, not replayed
- **WHEN** a per-move evaluation is assembled for a move that sits in the middle of a long recorded game
- **THEN** the input SHALL include at most the configured number of preceding and following agent moves, and SHALL NOT grow with the total number of moves in the game

#### Scenario: Window size is configurable including no hindsight
- **WHEN** an operator configures the following-moves window to zero
- **THEN** the judge input SHALL contain no moves recorded after the one being graded

#### Scenario: Round roll-up is graded against a board
- **WHEN** a round's closing sequence is an agent move, which carries no recorded state of its own
- **THEN** the round's judge input SHALL carry the nearest recorded state at or before that sequence rather than no state

## ADDED Requirements

### Requirement: Non-strategic actions are skipped with a recorded reason
The eval-service SHALL NOT spend a judge call on a recorded action that commits no game state a player could get wrong. The classification SHALL turn on whether the action commits game state in a way a player could get wrong, NOT on whether the underlying tool reads or writes: searching a card database cannot be a wrong decision, whereas taking a card into hand can be, so a search SHALL be treated as non-strategic while drawing or playing a card SHALL be evaluated.

The set of non-strategic actions SHALL be operator-configurable, and its default SHALL cover read-only queries, session and room plumbing, and pre-game setup that establishes the starting position. Any action outside the configured set — including every action name the service does not recognise — SHALL be evaluated, so that a new or renamed action can never be skipped by accident.

A skipped non-strategic target SHALL be recorded as `skipped` carrying a reason that names the action and why it was skipped, through the same per-target skip channel a judge failure uses, and SHALL NOT be recorded as completed and SHALL NOT have a verdict written to history. Skipping SHALL be possible to disable entirely by configuration.

A round-level or game-level roll-up SHALL exclude non-strategic moves from the moves it grades and SHALL state how many were excluded, so a roll-up score is not influenced by ungradeable actions. A roll-up whose span contains only non-strategic moves SHALL still be produced; the skip is a move-level judgement.

#### Scenario: Searching for a card is skipped, taking one into hand is not
- **WHEN** the eval-service evaluates a recorded move whose action is a card or set search
- **THEN** it SHALL record the target as `skipped` with a reason naming the action, SHALL NOT invoke the judge, and SHALL NOT write a verdict
- **AND WHEN** the recorded move's action instead draws a card into hand or plays a card
- **THEN** the eval-service SHALL evaluate it normally

#### Scenario: A skipped action cannot be mistaken for a passing verdict
- **WHEN** a client inspects an evaluation request that contained non-strategic targets
- **THEN** each such target SHALL appear with terminal status `skipped` and its stated reason, and SHALL NOT appear as completed or carry a score

#### Scenario: Unrecognised action is evaluated
- **WHEN** a recorded move names an action the service's taxonomy does not know
- **THEN** the eval-service SHALL evaluate it rather than skip it

#### Scenario: Skip set is configurable in both directions
- **WHEN** an operator supplies an explicit set of non-strategic action names
- **THEN** that set SHALL replace the built-in default, so an action the default skipped is evaluated unless it is listed
- **AND WHEN** an operator disables non-strategic skipping
- **THEN** every recorded move SHALL be evaluated

#### Scenario: Roll-up states what it left out
- **WHEN** a round roll-up's span contains non-strategic moves
- **THEN** those moves SHALL be omitted from the moves the judge is asked to grade and the input SHALL state how many were omitted
