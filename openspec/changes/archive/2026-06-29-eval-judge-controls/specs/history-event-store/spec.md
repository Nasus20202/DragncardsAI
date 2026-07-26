## ADDED Requirements

### Requirement: List games with recorded history

The history-service SHALL expose an endpoint listing every game that has recorded history, including the game identifier, its event count, and its first and last recorded timestamps, ordered by most recent activity, computed without a per-game query fan-out.

#### Scenario: Listing returns recorded games

- WHEN a client requests the games list and two games have recorded events
- THEN the response contains both games with their event counts and first/last recorded timestamps, ordered by last activity descending

#### Scenario: Listing is empty when nothing is recorded

- WHEN a client requests the games list and no events have been recorded
- THEN the response is an empty list

### Requirement: Delete a game's history

The history-service SHALL support deleting all recorded history for a game — its events, snapshots, and per-game bookkeeping — in a single transaction, reporting the counts removed, and SHALL be idempotent when the game has no history.

#### Scenario: Deleting removes events and snapshots

- WHEN a delete request is issued for a game that has recorded events and snapshots
- THEN all of that game's events and snapshots are removed in one transaction and the response reports the counts deleted

#### Scenario: Deleting an absent game is idempotent

- WHEN a delete request is issued for a game with no recorded history
- THEN the request succeeds and reports zero events and zero snapshots deleted
