## MODIFIED Requirements

### Requirement: Export and import controls in the history header

The dashboard history view SHALL offer an export control and an import control in its header action bar, styled as the header's existing actions are.

Each control SHALL ask its one question in a dialog rather than acting on the press. An export that always carried the prompt material had no way to produce a shareable bundle, and an import that always used the bundle's own game id conflicted on the common case — importing a bundle exported from a game the user still holds.

The export control SHALL be offered only while a game is selected. It SHALL open a dialog offering the two export modes, `full` and `minimal`, each named and described in terms of what it carries, and SHALL default to `full`. Confirming SHALL download that game's history bundle in the chosen mode by navigating to the history-service export endpoint rather than fetching and buffering it, so that a bundle running to tens of megabytes is streamed to disk by the browser instead of held in the tab. The download filename SHALL match the one the service declares, including the mode, so exporting a game both ways does not overwrite one file with the other.

The import control SHALL be offered whether or not a game is selected, because an import creates a game rather than modifying the selected one. It SHALL open a file picker restricted to bundle files. Picking a file SHALL open a dialog naming the picked file and offering the three import targets as a single choice — a game id the service mints, the id recorded in the bundle's own header, or an id the user types — because the service refuses a request that both names a target and asks for a new one. The default SHALL be the minted id, which is the only target that cannot conflict with a game that already has recorded history. The typed-id choice SHALL reveal a field for the id and SHALL NOT allow the import to proceed while that field is empty. The dialog SHALL indicate that an import is in progress and SHALL NOT allow the choice to be changed while it is.

The outcome of an import SHALL be reported inline in the history view — in the dashboard's existing notice style, since the dashboard has no toast layer — and never silently. A successful import SHALL state how many events and snapshots were written, under which game, and which mode the bundle declared, and SHALL select that game so its timeline is immediately visible. Naming the mode is what stops a minimal import's empty agent transcripts from reading as a broken import. When the target differs from the game the bundle was exported from and imported events still name that source game inside their payloads, the notice SHALL say how many do, because those payloads are recorded evidence and are deliberately never rewritten.

A rejected import SHALL surface the history-service's own message, including the line of the file at fault, as an alert, and SHALL NOT change the selected game. The dialog SHALL stay open on a rejection, so that a conflict on one target is answered by choosing another rather than by picking the file again.

#### Scenario: Export the selected game

- **WHEN** a game is selected and the user activates the export control and confirms a mode
- **THEN** the dashboard SHALL start a download from that game's export endpoint for that mode, and SHALL leave no download element behind in the document

#### Scenario: The export mode is a deliberate choice

- **WHEN** the export dialog is open
- **THEN** it SHALL offer both `full` and `minimal` with a description of what each carries, and SHALL preselect `full`

#### Scenario: Export is not offered without a selection

- **WHEN** no game is selected
- **THEN** the dashboard SHALL NOT offer the export control, and SHALL still offer the import control

#### Scenario: Picking a bundle asks where it should land

- **WHEN** the user picks a bundle file
- **THEN** the dashboard SHALL open a dialog naming that file and offering the three targets, with the service-minted id preselected, and SHALL NOT have sent the file anywhere yet

#### Scenario: Importing under a typed id

- **WHEN** the user chooses to name the target themselves
- **THEN** the dashboard SHALL reveal a field for the game id, SHALL keep the confirming action disabled while it is empty, and SHALL send the typed id as the import target

#### Scenario: A successful import is reported and opened

- **WHEN** the user picks a bundle file, chooses a target, and the history-service accepts it
- **THEN** the dashboard SHALL show a status notice stating the number of events and snapshots written, the game they were written to, and the mode the bundle declared, and SHALL select that game

#### Scenario: Remaining references to the source game are named

- **WHEN** an accepted import landed on a game id other than the one the bundle was exported from, and it reports events that still mention the source id
- **THEN** the notice SHALL say how many events still name the source game

#### Scenario: A rejected import is reported as an alert

- **WHEN** the user picks a bundle file and the history-service rejects it
- **THEN** the dashboard SHALL show the service's message — including the offending line — as an alert, SHALL NOT change the selected game, and SHALL leave the target dialog open so another target can be chosen
