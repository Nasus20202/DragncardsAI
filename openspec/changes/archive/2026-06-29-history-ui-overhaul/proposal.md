## Why

The history page is functionally rich but hard to use: the captured agent conversation is dumped as raw JSON (unreadable), there is no way to actually see/click the game board at a past moment, and the layout breaks when the (now larger) controls exceed the viewport. The Play tab already has polished transcript rendering, and the restore engine can already reconstruct the exact board at any event — this change reuses both to make history genuinely usable.

## What Changes

- **dashboard** SHALL render the captured agent conversation (messages, reasoning, tool calls/results) using the same transcript presentation as the Play tab, instead of raw JSON.
- **dashboard** SHALL let the user open the DragnCards board reconstructed at the selected event and click around it — by restoring that event's `seq` into a fresh (branchable) session and embedding its room — and SHALL tear that ephemeral reconstruction down when the view closes (component unmount and tab close), also removing any history it produced so the games list is not polluted.
- **dashboard** SHALL use a responsive, scroll-safe layout for the history page (timeline · detail/board · controls) that holds up at any window size.

## Capabilities

### Modified Capabilities

- `game-history-ui`: Play-parity conversation rendering, an on-demand reconstructed board view for the selected event with ephemeral-session teardown on close, and a responsive history-page layout.

## Impact

- dashboard only; reuses existing endpoints — restore (`POST /history/games/{id}/restore`), game-service `GET /games` (room_slug) and `DELETE /games/{session_id}`, history `DELETE /games/{game_id}`, and the Play transcript components. No new backend service endpoints.
- A best-effort TTL reaper for orphaned reconstruction sessions is noted as a follow-up (client teardown + history cleanup is the primary mechanism).
