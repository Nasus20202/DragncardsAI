## 1. Sidebar containment (board renders where it is placed)

- [x] 1.1 Make `HistoryGamesList`'s root flex within the sidebar column
      (`min-h-0 flex-1`) instead of `h-full`, so the games list and the navigation
      tree together fit the sidebar box and the overflow-hidden workspace row is
      no longer scrollable.
- [x] 1.2 Leave the sidebar's markup, classes, and `data-testid` values otherwise
      untouched — the games list, its toolbar, and the navigation tree render
      exactly as before.

## 2. Reconstruction lifecycle

- [x] 2.1 Drop the `visibilitychange` teardown from `useBoardReconstruction`; keep
      `pagehide` as the unload-safe disposal path and document why a hidden tab
      must not dispose a live board.

## 3. Ephemeral session teardown closes its room

- [x] 3.1 In `SessionManager.delete_session`, close the DragnCards room for
      ephemeral sessions before leaving the channel, best-effort (a failure is
      logged and does not abort the teardown). Both the client fast path and the
      TTL reaper go through this path.
- [x] 3.2 Leave non-ephemeral session deletion as it is: the room belongs to the
      user and only this client detaches from it.

## 4. Tests

- [x] 4.1 `history-layout.test.tsx`: the games list and the navigation tree are
      siblings in the sidebar and the list flexes (`min-h-0 flex-1`, never
      `h-full`), so the sidebar cannot overflow and displace the main panel.
- [x] 4.2 `board-reconstruction.test.tsx`: a hidden document does not dispose the
      live reconstruction (no DELETE, board still mounted) and an explicit close
      afterwards still tears it down.
- [x] 4.3 `test_session_manager.py`: deleting an ephemeral session pushes
      `close_room`; deleting a kept session does not; a failing room close still
      completes the teardown; the reaper closes the room too.

## 5. Verification

- [x] 5.1 Each new test fails against the pre-fix code and passes after it.
- [x] 5.2 `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build` in
      `services/dashboard/`; `./scripts/lint.sh --fix` and `./scripts/test.sh unit`
      at the repo root; game-service unit tests.
- [x] 5.3 Browser check against the running stack: open the board at an event and
      confirm the board's header and Close control are on screen and the board
      fills the main panel; the workspace row's `scrollTop` stays 0 through
      selecting a game, opening Actions, and opening the board.
