## Why

The DragnCards round loop can ask player agents to act while the board is still in setup/passive state. That leaves the round at the raw initial counter and causes valid player actions to be treated as illegal or undone; the orchestrator must enter the player phase before dispatching seat turns.

## What Changes

- Make the DragnCards round loop advance from setup/passive into the player phase before prompting any player seat.
- Keep the neutral `playRound` value sourced from the game-service state rather than applying a second consumer-side offset.
- Add regression coverage for the phase transition and the first player turn.
- Update the orchestrator's DragnCards round-loop reference so its entry condition matches the server behavior.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-orchestration`: require player-seat dispatch to begin only after the game is in the player phase, while preserving the platform-neutral round contract.

## Non-goals

- Changing Marvel Champions rules or player-agent decision making.
- Changing the neutral state normalizer or its `playRound` conversion.
- Changing villain-phase automation, seat authorization, or the separate `wait_for_subagent` and cross-game session-binding follow-ups.
- Adding support for another game platform.