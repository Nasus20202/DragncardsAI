## MODIFIED Requirements

### Requirement: Reconstructed board at the selected event

The dashboard SHALL let the user open the DragnCards board reconstructed at the selected event by restoring that event's `seq` into a fresh EPHEMERAL session (a non-emitting session that records no history) and embedding its room, allowing interaction, and SHALL dispose that ephemeral reconstruction when the view is closed — on in-app close/navigation and on browser tab close. Because the ephemeral session emits no history, disposal removes the reconstruction session only. Client disposal is best-effort (a server-side TTL reaper reclaims sessions whose client never tore them down). Only one reconstruction is live at a time.

A live reconstruction SHALL survive the browser tab merely becoming hidden — switching tabs, minimizing, or backgrounding the application is not the end of the view. Disposal is triggered by an in-app close, a change of selection or game, unmounting the view, and page unload (tab close, refresh, navigation), never by the document becoming hidden, so the board the user comes back to is still the board the dashboard claims is open.

#### Scenario: Open and click the board at a past moment

- WHEN the user opens the board for a selected event
- THEN the dashboard reconstructs that event's state into a fresh ephemeral session, embeds its DragnCards room, and the user can interact with the board as it was at that moment

#### Scenario: Reconstruction is disposed on close

- WHEN the user closes the reconstructed board view, navigates away, or closes the tab
- THEN the dashboard deletes the reconstruction session, leaving no orphaned session; because the ephemeral session is non-emitting, no extra game appears in the history list

#### Scenario: Reconstruction survives a hidden tab

- WHEN the user switches to another browser tab, minimizes the window, or backgrounds the application while a reconstruction is open
- THEN the dashboard keeps that reconstruction session alive, and returning to the tab shows the same live board rather than a board whose session has been deleted underneath it

### Requirement: Responsive history layout

The dashboard history page SHALL use a responsive layout (timeline, detail/board, and controls) that remains usable without clipping or horizontal overflow across window sizes, including when the judge configuration panel is expanded.

The sidebar's content SHALL fit inside the sidebar box, so the region that holds the sidebar and the main panel is never scrollable. That region does not scroll by design; if the sidebar's stacked sections (the games list and the navigation tree) overflow it, anything that scrolls an element into view — focusing a control, the transcript's auto-follow scroll — scrolls the region instead and displaces the whole main panel, pushing the reconstructed board's header and Close control off screen.

#### Scenario: Layout holds on resize

- WHEN the history page is resized to a smaller or larger window
- THEN the timeline, detail/board, and controls remain reachable and scrollable without horizontal overflow or clipped content

#### Scenario: Opening the board does not displace the main panel

- WHEN the user selects a game, opens an event's actions, and opens the reconstructed board
- THEN the sidebar+main region's scroll offset stays at its origin and the board renders fully inside the main panel, with its header and Close control on screen
