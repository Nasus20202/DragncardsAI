## Why

Multiplayer history currently renders every agent move as a generic `Agent`, so readers cannot tell which seat made a decision. Move-scoped evaluation also assembles neighbouring moves from every seat, leaking unrelated strategy into the judge context and weakening per-player grading.

## What Changes

- Display the recorded player id on attributed agent move entries in the History transcript.
- Restrict move-scoped neighbouring context to the target player's agent moves.
- Preserve aggregate neighbouring context for legacy chat moves that have no player attribution.
- Add regression coverage for player labels and cross-seat context isolation.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-history-ui`: identify the player responsible for each attributed agent move.
- `agent-move-evaluation`: keep move-scoped neighbouring context within the evaluated player's seat.

## Non-goals

- Changing event attribution or persistence contracts.
- Changing round/game roll-up context, verdict fan-out, or evaluator scoring criteria.
- Requiring player labels for legacy events that do not carry a player id.
