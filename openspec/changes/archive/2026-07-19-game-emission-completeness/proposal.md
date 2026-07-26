# Complete game-state history emission across mutating operations

## Why

The design contract is "a `game_state` history event after each mutating action",
so the recorded timeline can be replayed and inspected board-by-board. Today the
Game Service only emits from `execute_action`. Three other operations mutate game
state through the same room but never emit a `game_state` event:

- `load_prebuilt_deck` — deals an entire deck (a large board change).
- `load_state` — replaces the whole game state from a snapshot.
- `reset_game` — resets (or resets-and-reloads) the game.

The result is gaps in the recorded timeline: e.g. the board immediately after a
deck load is never snapshotted, even though the orchestrator records the
corresponding `agent_move`. This leaves history unable to show/restore the state
that actually resulted from those operations.

## What Changes

- After each of `load_prebuilt_deck`, `load_state`, and `reset_game` successfully
  applies its mutation and has the fresh resulting state, emit exactly one
  `game_state` history event via the same `_emit_history_state_event` path used
  by `execute_action` (same session layer; no double-emission).
- The deck load carries its replayable raw `LOAD_CARDS` action so restore can
  replay it forward; the snapshot load and the reset carry no replayable action
  (they are not `POST /actions` operations) and emit a state-only event.
- Emission stays strictly best-effort and isolated: a history-emission failure
  never aborts or alters the underlying game operation, mirroring how
  `execute_action` isolates emission. Ephemeral (view-only) sessions and
  rejected/aborted operations still emit nothing.
- Read-only operations (`get_state`, `export_state`) continue to emit nothing.

This is a game-service-only change; the history envelope contract is unchanged.

## Impact

- Affected specs: `game-service` (MODIFIED: Game-state and status event emission).
- Affected code: `services/game-service/src/game_service/logic/session.py`
  (`load_prebuilt_deck`, `load_state`, `reset_game`).
- Affected tests: `services/game-service/tests/unit/test_history_emitter.py`.
- Behavior change: a branchable restore that loads a snapshot now records the
  loaded board as an initial `game_state` event; ephemeral view sessions are
  unaffected (they never emit).
