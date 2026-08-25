# Make recorded history reads platform-aware

## Why

History is stored in independent `(game_id, platform)` series. The history-service
read endpoints already accept a platform filter, but the dashboard's history client
does not send the selected game's platform when loading its timeline, snapshots, or
full event details. The service therefore applies its backward-compatible
`dragncards` default to a `marvel-lcg` game and returns an empty timeline even though
the game has recorded events.

## What Changes

- Carry the selected history game's platform through dashboard timeline, snapshot,
  full-event, and deletion requests.
- Preserve the history-service's `dragncards` default for older callers that do not
  provide a platform.
- Keep history emission best-effort for gameplay while logging platform-emission
  failures with the game and event identifiers needed to diagnose missing records.
- Add regression coverage for platform-specific dashboard URLs and the history
  hook's selected-platform propagation and platform-specific deletion.

## Impact

- Affected specs: `game-history-ui` (MODIFIED: recorded-game selection loads the
  selected platform's timeline) and `game-service` (ADDED: platform history
  emission failures are observable without changing gameplay).
- Affected code: dashboard history API, history hook, workspace, and transcript
  detail loading.
- The game-service producer and history-service storage contract remain unchanged;
  both already record and store `dragncards` and `marvel-lcg` events separately.
