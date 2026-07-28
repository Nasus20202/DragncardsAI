# Make the history viewer's reconstructed board load and display reliably

## Why

Opening "Board at this event" in the History tab reconstructs the right moment —
the restore succeeds, the ephemeral session is created, `room_slug` resolves, and
the embedded DragnCards room shows exactly the recorded state — and then the user
cannot see it. Measured against the running stack (viewport 1280×720, a game with
19 recorded events):

- Clicking an event's **Actions** toggle scrolls the workspace's sidebar+main row
  to `scrollTop: 25`; clicking **Open board at this event** drives it the rest of
  the way to its maximum, `282`. The board's container then sits at
  `top: -189, bottom: 438` — its "Board at event #N" header and the **Close
  board** button are above the top of the window, the top third of the board is
  clipped, and 282px of dead space sits under it. Forcing that row back to
  `scrollTop: 0` puts the board at `top: 93, bottom: 720`: a full, correct board.

  The row is `overflow-hidden` and is not meant to scroll at all, but it is
  scrollable because the sidebar overflows it (`clientHeight: 627`,
  `scrollHeight: 909`). The sidebar renders two children — the games list and the
  navigation tree — and the games list claims `h-full` (the sidebar's whole
  height) while the tree adds up to another 45% below it. Anything that scrolls an
  element into view (focusing the Actions control, the transcript's auto-follow
  scroll-to-bottom) therefore scrolls that row and displaces the entire main
  panel, the board included.

- The reconstruction is also torn down when the browser tab merely becomes
  hidden. Reproduced by hiding the document: the game-service session disappears
  from `GET /games` while the dashboard still renders the board as live. Switching
  browser tabs, minimizing the window, or backgrounding the app is not the end of
  the view; it left the embedded room orphaned (no session to reap it) and the UI
  claiming a reconstruction that no longer existed.

- Teardown never released the reconstruction's DragnCards room. Deleting an
  ephemeral session only left its Phoenix channel and disconnected, so the room
  survived: after tearing down two reconstructions, `maniacal-guide-6252` and
  `fast-light-6795` were both still rows in the DragnCards `rooms` table. Every
  board opened leaked a room permanently, in both the client fast path and the TTL
  reaper — despite the reaper's own docstring ("Delete a single ephemeral session
  + its room") and the existing requirement that a reclaimed reconstruction has
  "their session state and DragnCards room deleted".

## What Changes

- **dashboard (sidebar containment)** — the history games list SHALL flex within
  the sidebar column (`min-h-0 flex-1`) instead of claiming its full height, so
  the sidebar's content stays inside the sidebar box, the workspace row is not
  scrollable, and no scroll-into-view can displace the main panel or the
  reconstructed board. Nothing else about the sidebar's appearance changes.
- **dashboard (reconstruction survives a hidden tab)** — the reconstruction
  lifecycle SHALL dispose on `pagehide` only, not on `visibilitychange`. Tab
  close, refresh, and navigation still tear the session down through the same
  unload-safe transport; a tab switch or backgrounded window leaves the live board
  alone, and the server-side TTL reaper remains the safety net.
- **game-service (reconstruction owns its room)** — deleting an **ephemeral**
  session SHALL close its DragnCards room before leaving the channel, so both the
  client fast path and the TTL reaper actually reclaim the room. Room closing is
  best-effort: a failure is logged and the rest of the teardown still completes.
  Deleting a kept (non-ephemeral) session is unchanged — that room belongs to the
  user and only this client detaches from it.

## Non-goals

- Any restyling of the history view. The existing dashboard is the visual
  reference; the only layout token that changes is the one that made the sidebar
  overflow its own box.
- Changing what the board shows or how the state is reconstructed. Verified
  correct: restoring event #10 of a 19-event game loaded exactly that moment
  (deck 34, discard 4, step 0.0) rather than the latest state.
- Reworking how the board replaces the transcript in the main panel, or giving the
  reconstruction its own route or window.
- Cleaning up DragnCards rooms orphaned by ordinary (non-ephemeral) play sessions.

## Impact

- Affected specs: `game-history-ui` (reconstruction disposal triggers; responsive
  layout gains sidebar containment), `game-service` (ephemeral session deletion
  closes its room). `history-event-store` already requires the room to be deleted
  with the reconstruction — the game-service change makes the implementation match
  it, so that spec is unchanged.
- Affected code:
  `services/dashboard/features/history/components/history-games-list.tsx`,
  `services/dashboard/features/history/lib/use-board-reconstruction.ts`,
  `services/game-service/src/game_service/logic/session_manager.py`.
- No API, schema, or configuration changes.
