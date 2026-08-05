## MODIFIED Requirements

### Requirement: Reconstructed board at the selected event

The dashboard SHALL let the user open the DragnCards board reconstructed at the selected event by restoring that event's `seq` into an EPHEMERAL session (a non-emitting session that records no history) and embedding its room, allowing interaction, and SHALL dispose that ephemeral reconstruction when the view is closed — on in-app close/navigation and on browser tab close. Because the ephemeral session emits no history, disposal removes the reconstruction session only. Client disposal is best-effort (a server-side TTL reaper reclaims sessions whose client never tore them down). Only one reconstruction is live at a time.

A live reconstruction SHALL survive the browser tab merely becoming hidden — switching tabs, minimizing, or backgrounding the application is not the end of the view. Disposal is triggered by an in-app close, a change of game, unmounting the view, and page unload (tab close, refresh, navigation), never by the document becoming hidden, so the board the user comes back to is still the board the dashboard claims is open.

When only the selected event changes within the same game, the dashboard SHALL retain the ephemeral session rather than dispose it, and SHALL restore the newly selected event into that retained session instead of building a second room. Building a room is several sequential round trips to DragnCards plus a channel join and a plugin load; re-pointing an open room at another moment is a single state load, measured at ~55 ms against ~728 ms. Retention is what makes viewing a second moment fast, and it is safe because loading a full-state base replaces the room's game document outright.

Retaining the session SHALL NOT mean retaining the rendered board. When the selection moves, the dashboard SHALL clear the displayed reconstruction so that a board is never shown under a header naming a different moment, and the user SHALL re-open deliberately. A retained session SHALL be disposed on in-app close, a change of game, unmount, and page unload, exactly as a displayed one is, so retention never outlives the panel.

The reconstruction view SHALL state, on the view itself, that it is a temporary copy which does not affect the recorded game and is discarded when closed. This view replaces the whole transcript panel with an unfamiliar DragnCards room, and a board that looks exactly like a live game is indistinguishable from one; leaving the user to infer that nothing was overwritten produced a report of data loss against behaviour that provably changes nothing.

The dashboard SHALL explain the wait while a reconstruction is being built, rather than showing an unqualified spinner. Building one creates a real DragnCards room — several sequential round trips to the DragnCards backend plus a channel join and a plugin load, seconds rather than milliseconds — and an unexplained multi-second wait on a button whose effect the user is already unsure of is a substantial part of the surface reading as slow and unclear.

The dashboard SHALL take the reconstruction's room from the restore response when the history-service supplies it, rather than listing every live session and searching it by id. The list read is retained only as a fallback for a service that reports no room. Beyond the wasted round trip, the search races the ephemeral reaper: a session reclaimed between the restore and the list yields no match, and the view then renders its fallback with no error surfaced. When a retained session is reused, the room is already known from the open that created it, so the dashboard SHALL keep using that room and SHALL NOT list sessions to rediscover it.

#### Scenario: Open and click the board at a past moment
- WHEN the user opens the board for a selected event
- THEN the dashboard reconstructs that event's state into an ephemeral session, embeds its DragnCards room, and the user can interact with the board as it was at that moment

#### Scenario: A second moment of the same game reuses the open room
- WHEN the user has a reconstruction open, selects a different event of the same game, and opens the board again
- THEN the dashboard SHALL restore into the session it already holds, SHALL embed the same room, and SHALL NOT create a second DragnCards room

#### Scenario: A reused board shows the newly selected moment
- WHEN a retained session is re-pointed at a different event
- THEN the embedded board SHALL show the state at the newly selected event, carrying nothing over from the moment it previously showed

#### Scenario: Moving the selection clears the board but keeps the session
- WHEN the user changes the selected event while a reconstruction is displayed
- THEN the dashboard SHALL stop displaying the board so that no board is shown under a header naming another moment, and SHALL keep the session so that re-opening reuses it

#### Scenario: Switching game disposes the retained session
- WHEN the user selects a different game while a reconstruction session is retained, whether displayed or not
- THEN the dashboard SHALL dispose that session, because a session built for one game cannot be re-pointed at another

#### Scenario: The reconstruction says it is a throwaway copy
- WHEN a reconstructed board is shown
- THEN the view SHALL state that it is a temporary copy, that the recorded game is unaffected by anything done in it, and that it is discarded on close

#### Scenario: The wait while a board is built is explained
- WHEN a reconstruction is being created
- THEN the dashboard SHALL say that a temporary DragnCards room is being created and that it takes a few seconds, rather than showing only a spinner

#### Scenario: The room comes from the restore response
- WHEN a restore for a reconstruction reports the new session's room
- THEN the dashboard SHALL embed that room without listing the live sessions, falling back to the session list only when no room is reported

#### Scenario: A reused session does not re-resolve its room
- WHEN a restore reuses a retained session and therefore reports no newly created room
- THEN the dashboard SHALL embed the room it already recorded for that session and SHALL NOT list the live sessions

#### Scenario: Disposal on close
- WHEN the user closes the reconstructed board view, navigates away, or closes the tab
- THEN the dashboard deletes the reconstruction session, leaving no orphaned session; because the ephemeral session is non-emitting, no extra game appears in the history list

#### Scenario: A hidden tab does not end the view
- WHEN the browser tab holding a live reconstruction becomes hidden
- THEN the dashboard keeps that reconstruction session alive, and returning to the tab shows the same live board rather than a board whose session has been deleted underneath it
