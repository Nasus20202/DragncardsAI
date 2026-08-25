## MODIFIED Requirements

### Requirement: History-driven game picker with delete

The dashboard history view SHALL source its game picker from games-with-recorded-history and SHALL provide a control to delete all history for the selected game, with a confirmation step, refreshing the picker and clearing the selection after a successful deletion. When a selected game declares a platform, every timeline, snapshot, complete-event, and deletion request SHALL request that platform so the view reads and manages the selected game's `(game_id, platform)` history series rather than relying on the history-service's `dragncards` compatibility default.

#### Scenario: Picking a recorded game

- WHEN the user opens the history view
- THEN the game picker lists games that have recorded history and selecting one loads its timeline for the platform reported by that game

#### Scenario: Reading a Marvel LCG game's history

- WHEN the selected recorded game has platform `marvel-lcg`
- THEN the dashboard SHALL include `platform=marvel-lcg` when loading its timeline, snapshots, and complete event payloads
- AND the dashboard SHALL display the events recorded for that Marvel LCG game

#### Scenario: Reading legacy DragnCards history

- WHEN the selected recorded game has no platform field or platform `dragncards`
- THEN the dashboard SHALL continue to read the DragnCards history series using the history-service compatibility default

#### Scenario: Deleting a Marvel LCG game's history

- WHEN the user deletes the selected Marvel LCG game's history and confirms
- THEN the dashboard SHALL include `platform=marvel-lcg` on the delete request
- AND the Marvel LCG history SHALL be removed without deleting a DragnCards series with the same identifier

#### Scenario: Deleting a game's history

- WHEN the user deletes the selected game's history and confirms
- THEN the dashboard calls the delete endpoint, clears the selection, and refreshes the game list so the deleted game no longer appears
