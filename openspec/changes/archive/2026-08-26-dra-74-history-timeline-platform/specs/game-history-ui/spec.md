## MODIFIED Requirements

### Requirement: History-driven game picker with delete

The dashboard history view SHALL source its game picker from games-with-recorded-history and SHALL provide a control to delete all history for the selected game, with a confirmation step, refreshing the picker and clearing the selection after a successful deletion. The selected history identity SHALL be the pair `(game_id, platform)`, with `dragncards` used when a game list entry has no platform. Every timeline page, incremental timeline page, complete-event detail request, snapshot request, export request, and deletion request SHALL use that identity rather than relying on the history-service's `dragncards` compatibility default.

#### Scenario: Picking a recorded game

- WHEN the user opens the history view
- THEN the game picker SHALL list games that have recorded history and selecting one SHALL load its timeline for the platform reported by that game

#### Scenario: Reading a selected Marvel LCG game with recorded events

- WHEN the game picker reports a selected `marvel-lcg` game with a nonzero `event_count`
- THEN the dashboard SHALL request its timeline pages, complete event details, snapshots, and exports with `platform=marvel-lcg`
- AND the transcript SHALL render the events in that Marvel LCG history series rather than the empty state for the DragnCards partition

#### Scenario: Incremental Marvel LCG refresh keeps the partition

- WHEN the dashboard refreshes a selected Marvel LCG game's timeline after a previously loaded sequence
- THEN every cursor request SHALL include both the `after_seq` cursor and `platform=marvel-lcg`

#### Scenario: Reading legacy DragnCards history

- WHEN the selected recorded game has no platform field or platform `dragncards`
- THEN the dashboard SHALL read its timeline, complete events, snapshots, and export through the DragnCards compatibility default

#### Scenario: Deleting a Marvel LCG game's history

- WHEN the user deletes the selected Marvel LCG game's history and confirms
- THEN the dashboard SHALL include `platform=marvel-lcg` on the delete request
- AND the Marvel LCG history SHALL be removed without deleting a DragnCards series with the same identifier

#### Scenario: Deleting a game's history

- WHEN the user deletes the selected game's history and confirms
- THEN the dashboard SHALL call the delete endpoint, clear the selection, and refresh the game list so the deleted game no longer appears
