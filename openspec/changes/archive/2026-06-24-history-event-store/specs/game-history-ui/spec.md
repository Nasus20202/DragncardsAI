## ADDED Requirements

### Requirement: Game history timeline view
The dashboard SHALL provide a view that lists a game's history as an ordered timeline of events and snapshots retrieved from the history-service.

#### Scenario: Display ordered timeline for a game
- **WHEN** a user opens the history view for a `game_id`
- **THEN** the dashboard SHALL display the game's events ordered by ascending `seq`, distinguishing `agent` move/decision events from `game-service` game-state events

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

### Requirement: Restore-to-a-past-moment control
The dashboard SHALL provide a control to trigger a restore of a game to a selected past moment through the history-service, letting the user choose the restore target mode (a new branchable session or an in-place overwrite of the live session).

#### Scenario: Trigger a restore from the timeline
- **WHEN** a user selects a timeline moment and confirms a restore
- **THEN** the dashboard SHALL request the history-service to restore the game to that moment's `seq` and SHALL show the restore outcome

#### Scenario: Choose the restore target mode
- **WHEN** a user initiates a restore to a selected moment
- **THEN** the dashboard SHALL let the user choose between a new branchable session and an in-place overwrite, defaulting to a new session, and SHALL pass the chosen mode to the history-service

#### Scenario: Warn before an in-place overwrite
- **WHEN** a user selects the in-place overwrite mode for a restore
- **THEN** the dashboard SHALL warn that game state after the selected moment will be discarded and SHALL require confirmation before proceeding

#### Scenario: Surface restore failure
- **WHEN** the history-service reports that a restore could not be completed
- **THEN** the dashboard SHALL display the failure to the user without claiming the restore succeeded
