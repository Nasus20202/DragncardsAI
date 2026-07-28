## ADDED Requirements

### Requirement: Export and import controls in the history header

The dashboard history view SHALL offer an export control and an import control in its header action bar, styled as the header's existing actions are.

The export control SHALL be offered only while a game is selected, and SHALL download that game's history bundle by navigating to the history-service export endpoint rather than fetching and buffering it, so that a bundle running to tens of megabytes is streamed to disk by the browser instead of held in the tab.

The import control SHALL be offered whether or not a game is selected, because an import creates a game rather than modifying the selected one. It SHALL open a file picker restricted to bundle files, SHALL send the picked file as the import request body, and SHALL indicate that an import is in progress.

The outcome of an import SHALL be reported inline in the history view — in the dashboard's existing notice style, since the dashboard has no toast layer — and never silently. A successful import SHALL state how many events and snapshots were written and under which game, and SHALL select that game so its timeline is immediately visible. A rejected import SHALL surface the history-service's own message, including the line of the file at fault, as an alert, and SHALL NOT change the selected game.

#### Scenario: Export the selected game

- **WHEN** a game is selected and the user activates the export control
- **THEN** the dashboard SHALL start a download from that game's export endpoint, and SHALL leave no download element behind in the document

#### Scenario: Export is not offered without a selection

- **WHEN** no game is selected
- **THEN** the dashboard SHALL NOT offer the export control, and SHALL still offer the import control

#### Scenario: A successful import is reported and opened

- **WHEN** the user picks a bundle file and the history-service accepts it
- **THEN** the dashboard SHALL show a status notice stating the number of events and snapshots written and the game they were written to, and SHALL select that game

#### Scenario: A rejected import is reported as an alert

- **WHEN** the user picks a bundle file and the history-service rejects it
- **THEN** the dashboard SHALL show the service's message — including the offending line — as an alert, and SHALL NOT change the selected game
