# game-history-ui spec delta

## MODIFIED Requirements

### Requirement: Restore-to-a-past-moment control

The dashboard SHALL provide a control to trigger a restore of a game to a selected past moment through the history-service, letting the user choose the restore target mode (a new branchable session or an in-place overwrite of the live session).

Each action available on a recorded moment SHALL state what it will do, to which game, **before** it is clicked, and a destructive action SHALL be distinguishable from a read-only one without clicking either. The three per-moment actions differ in exactly the way a user cares about — one changes nothing, one creates a second game, one destroys play from the game in front of them — and they were presented as an undifferentiated list of controls whose labels named mechanisms ("New branchable session", "In-place overwrite") rather than consequences. A user who cannot tell which action overwrites their game is the reported defect, and a read-only action that looks destructive gets reported as data loss.

The read-only action SHALL be offered first, ahead of the actions that change a game: looking at the board is the cheapest and most common thing a user wants from a recorded moment.

A restore's reported outcome SHALL name the thing it produced, in terms the user can act on. For a branch restore that means naming the DragnCards room that was created and offering a way to open it — a new game the user cannot reach is indistinguishable from a restore that did not happen. For an in-place restore it means saying that this game has been rewound.

The dashboard SHALL distinguish a restore that completed without its agent conversation from a restore that failed. When the history-service reports that the game state was restored but the agent context was not, the dashboard SHALL present that as a completed restore carrying an explanatory note, NOT as a failure — the game state really was changed, so calling it a failure describes a state that does not exist and invites the user to retry a destructive action that already succeeded.

A confirmation affordance SHALL name the action until the user asks to perform it, and only then present the confirmation wording. A control that opens already reading "Confirm overwrite" and changes to the action name after the first click shows its most alarming wording at the moment it is least warranted, and gives no indication that a second click is what commits.

#### Scenario: Trigger a restore from the timeline
- **WHEN** a user selects a timeline moment and confirms a restore
- **THEN** the dashboard SHALL request the history-service to restore the game to that moment's `seq` and SHALL show the restore outcome

#### Scenario: Choose the restore target mode
- **WHEN** a user initiates a restore to a selected moment
- **THEN** the dashboard SHALL let the user choose between a new branchable session and an in-place overwrite, defaulting to a new session, and SHALL pass the chosen mode to the history-service

#### Scenario: Each mode's effect is legible before it is chosen
- **WHEN** the per-moment actions are shown for an event
- **THEN** each SHALL carry a label naming its effect and a marker distinguishing read-only from safe-but-creating from destructive, and the read-only action SHALL appear first

#### Scenario: Warn before an in-place overwrite
- **WHEN** a user selects the in-place overwrite mode for a restore
- **THEN** the dashboard SHALL warn that game state after the selected moment will be discarded and SHALL require confirmation before proceeding, with the submit affordance naming the action until the user requests it and only then reading as a confirmation

#### Scenario: A branch restore names and links the game it created
- **WHEN** a restore into a new session completes and the history-service reports the new room
- **THEN** the dashboard SHALL name that room in the outcome and SHALL offer a link that opens it

#### Scenario: A restore without its agent conversation is not a failure
- **WHEN** the history-service reports a completed restore whose agent context was not rebuilt, with a reason
- **THEN** the dashboard SHALL present a completed restore and show the reason as a note, and SHALL NOT present it as a failed restore

#### Scenario: Surface restore failure
- **WHEN** the history-service reports that a restore could not be completed
- **THEN** the dashboard SHALL display the failure to the user without claiming the restore succeeded

### Requirement: Reconstructed board at the selected event

The dashboard SHALL let the user open the DragnCards board reconstructed at the selected event by restoring that event's `seq` into a fresh EPHEMERAL session (a non-emitting session that records no history) and embedding its room, allowing interaction, and SHALL dispose that ephemeral reconstruction when the view is closed — on in-app close/navigation and on browser tab close. Because the ephemeral session emits no history, disposal removes the reconstruction session only. Client disposal is best-effort (a server-side TTL reaper reclaims sessions whose client never tore them down). Only one reconstruction is live at a time.

A live reconstruction SHALL survive the browser tab merely becoming hidden — switching tabs, minimizing, or backgrounding the application is not the end of the view. Disposal is triggered by an in-app close, a change of selection or game, unmounting the view, and page unload (tab close, refresh, navigation), never by the document becoming hidden, so the board the user comes back to is still the board the dashboard claims is open.

The reconstruction view SHALL state, on the view itself, that it is a temporary copy which does not affect the recorded game and is discarded when closed. This view replaces the whole transcript panel with an unfamiliar DragnCards room, and a board that looks exactly like a live game is indistinguishable from one; leaving the user to infer that nothing was overwritten produced a report of data loss against behaviour that provably changes nothing.

The dashboard SHALL explain the wait while a reconstruction is being built, rather than showing an unqualified spinner. Building one creates a real DragnCards room — several sequential round trips to the DragnCards backend plus a channel join and a plugin load, seconds rather than milliseconds — and an unexplained multi-second wait on a button whose effect the user is already unsure of is a substantial part of the surface reading as slow and unclear.

The dashboard SHALL take the reconstruction's room from the restore response when the history-service supplies it, rather than listing every live session and searching it by id. The list read is retained only as a fallback for a service that reports no room. Beyond the wasted round trip, the search races the ephemeral reaper: a session reclaimed between the restore and the list yields no match, and the view then renders its fallback with no error surfaced.

#### Scenario: Open and click the board at a past moment
- WHEN the user opens the board for a selected event
- THEN the dashboard reconstructs that event's state into a fresh ephemeral session, embeds its DragnCards room, and the user can interact with the board as it was at that moment

#### Scenario: The reconstruction says it is a throwaway copy
- WHEN a reconstructed board is shown
- THEN the view SHALL state that it is a temporary copy, that the recorded game is unaffected by anything done in it, and that it is discarded on close

#### Scenario: The wait while a board is built is explained
- WHEN a reconstruction is being created
- THEN the dashboard SHALL say that a temporary DragnCards room is being created and that it takes a few seconds, rather than showing only a spinner

#### Scenario: The room comes from the restore response
- WHEN a restore for a reconstruction reports the new session's room
- THEN the dashboard SHALL embed that room without listing the live sessions, falling back to the session list only when no room is reported

#### Scenario: Disposal on close
- WHEN the user closes the reconstructed board view, navigates away, or closes the tab
- THEN the dashboard deletes the reconstruction session, leaving no orphaned session; because the ephemeral session is non-emitting, no extra game appears in the history list

#### Scenario: A hidden tab does not end the view
- WHEN the browser tab holding a live reconstruction becomes hidden
- THEN the dashboard keeps that reconstruction session alive, and returning to the tab shows the same live board rather than a board whose session has been deleted underneath it
