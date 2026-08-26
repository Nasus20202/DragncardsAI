## Why

The history service returns a distinct record for each `(game_id, platform)` pair.
When games on different platforms share an identifier, the dashboard renders two
sibling rows with the same React key, which can cause either row to be omitted or
duplicated.

## What Changes

- Carry the History identity `(game_id, platform)` through list keys, selection,
  deletion, deep links, restore, reconstruction, and evaluation requests.
- Add regression coverage for two platform records that share a game id.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The existing `game-history-ui` specification already defines a selected
history identity as `(game_id, platform)`; this change corrects the implementation
of that identity in React rendering without changing the user-facing contract.

## Impact

- Dashboard History identity helpers, workspace, list, reconstruction, and
  evaluation-control components.
- Dashboard History picker, deep-link, and platform-propagation tests.

## Non-goals

- Deduplicating records returned by history-service.
- Changing game labels, selection, deletion, or history API contracts.
