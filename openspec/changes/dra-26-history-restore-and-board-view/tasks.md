# Tasks

## 1. Establish current behaviour before changing anything

- [x] 1.1 Reproduce each of DRA-26's three claims against the running stack rather than reasoning from source, and record which are real.
- [x] 1.2 Locate the 404: confirm agent-orchestrator `POST /sessions/restore` answers `404` for `mode="in_place"` when no ACTIVE session is bound to the `game_id`, by calling it directly.
- [x] 1.3 Confirm the population this affects: count orchestrator session statuses and check whether the game with the richest recorded history has an active session bound to it.
- [x] 1.4 Trace how that `404` reaches the user — `raise_for_status()` in `integrations/orchestrator.py`, the broad `except Exception` in `_restore` — and establish that the live game has already been rewound by then with no rollback for `in_place`.
- [x] 1.5 Test the branch mode end to end: confirm whether a new DragnCards game and new history really are created, and identify what is actually missing.
- [x] 1.6 Test the board mode by capturing the original game's state before and after and comparing byte-for-byte; confirm the reconstruction is flagged ephemeral and emits no history.
- [x] 1.7 Measure where the time goes in one "open board" click — per-query payload sizes, HTTP round-trip count, and the DragnCards round-trip floor — so the slowness claim is answered with numbers.

## 2. history-service: make an in-place restore survive a missing agent session

- [x] 2.1 Return `(session_id, note)` from `_restore_agent_context` and tolerate a `404` from the orchestrator, letting the completed game-state restore stand.
- [x] 2.2 Keep every other upstream status fatal, so a `500` is not silently swallowed.
- [x] 2.3 Carry `agent_context_restored` and `agent_context_note` on `RestoreResult`, `RestoreResponse`, and the router.
- [x] 2.4 Test the tolerated `404` and, separately, that a `500` still fails the restore.

## 3. history-service: report a deleted live session instead of a bare 404

- [x] 4.1 Wrap the base load in `_load_base` and map an in-place `404` to a message naming the cause and the branchable alternative.
- [x] 4.2 Test that the message names both, and that nothing was replayed onto a session that does not exist.

## 4. history-service: let an in-place rewind use a `game_state` event as its base

- [x] 4.1 Resolve the base once for both modes via `_choose_base`; make `plugin_name` required only for a branch restore.
- [x] 4.2 Keep rejecting an in-place rewind that has no full-state base of either kind, and name what is missing.
- [x] 4.3 Test an in-place rewind of a game with no snapshot, and re-point the existing "no base snapshot" test at the new semantics.

## 5. history-service: carry the branch room slug

- [x] 5.1 Return `BranchSession(session_id, room_slug)` from `GameServiceClient.create_session` instead of discarding the slug `POST /games` already returns.
- [x] 5.2 Thread `room_slug` through `RestoreResult`, `RestoreResponse`, and the router.
- [x] 5.3 Update the three test fakes to the new return type.
- [x] 5.4 Test that a branch restore reports the slug and an in-place restore does not.

## 6. history-service: remove the measured payload waste

- [x] 6.1 Add an optional `actor` to `get_events_in_range` and pass `"game-service"` from restore; document the measured cost of not doing so.
- [x] 6.2 Bound the `_resolve_plugin_name` snapshot fallback with `limit=1`.
- [x] 6.3 Test that the replay range read is actually filtered, rather than trusting the call site.

## 7. dashboard: say what each action does

- [x] 7.1 Relabel the two restore modes to name consequences, and mark them `Safe` / `Destructive`.
- [x] 7.2 Relabel the board action, mark it `Read-only`, and state that the game is unchanged and the copy discarded.
- [x] 7.3 Name the action on the submit button instead of "Restore".
- [x] 7.4 Fix the inverted confirmation label so it names the action first and confirms only once armed.
- [x] 7.5 Put the read-only action first in the popover and widen it to fit the copy.

## 8. dashboard: report what a restore produced

- [x] 8.1 Name the created room and render an "Open the new game" link for a branch restore.
- [x] 8.2 Say the live game was rewound for an in-place restore.
- [x] 8.3 Show `agent_context_note` as a note on a successful restore, never as a failure.
- [x] 8.4 Extend `RestoreOutcome` with `room_slug`, `agent_context_restored`, `agent_context_note`.
- [x] 8.5 Thread `frontendUrl` to the restore control through the room-context bundle.

## 9. dashboard: the board view and its wait

- [x] 9.1 Add the `Temporary copy` chip and the throwaway-copy notice to `BoardView`.
- [x] 9.2 Replace the bare opening spinner with "Building the board…" plus an explanation of the wait.
- [x] 9.3 Take the room from the restore response, keeping the session list strictly as a fallback.
- [x] 9.4 Test the fast path (no session list read) and the fallback path.

## 10. Verify

- [x] 10.1 `./scripts/lint.sh --fix` then `./scripts/lint.sh` — exit 0.
- [x] 10.2 `./scripts/test.sh unit` — record per-service counts before and after.
- [x] 10.3 `pnpm typecheck` in `services/dashboard`.
- [x] 10.4 `./scripts/test.sh integration history-service`.
- [x] 10.5 `openspec validate dra-26-history-restore-and-board-view --strict` and `openspec validate --all`.
- [x] 10.6 Drive all three modes in the browser against real recorded history: the 404 is gone and an in-place rewind replaces the live state; branch mode creates a new DragnCards game with its own history; opening a board leaves the original game's state byte-identical.
- [x] 10.7 Delete every game and session created during verification, and say so.

## 11. Keep the surrounding files current

- [x] 11.1 Document the restore response's new fields and the tolerated `404` in `services/history-service/README.md`.
- [x] 11.2 Confirm no change is needed to `docker-compose.yaml`, `.env.example`, OTel configuration, `scripts/`, or the Swagger index, and say why in the proposal.
