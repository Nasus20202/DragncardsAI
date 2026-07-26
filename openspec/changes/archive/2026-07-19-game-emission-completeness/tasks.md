## 1. Emit game_state events from remaining mutating operations

- [x] 1.1 `load_prebuilt_deck`: clear the prior action error, build the replayable
      raw `LOAD_CARDS` action, and after the fresh state is observed emit one
      `game_state` event via `_emit_history_state_event` carrying that action.
- [x] 1.2 `load_state`: clear the prior action error and after the fresh state is
      observed emit one state-only `game_state` event (no replayable action).
- [x] 1.3 `reset_game`: clear the prior action error and after the fresh state is
      observed emit one state-only `game_state` event (no replayable action).
- [x] 1.4 Keep emission best-effort and isolated (reuse `_emit_history_state_event`,
      which already swallows offset/emit failures and skips ephemeral/aborted).
- [x] 1.5 Do not emit for read-only `get_state` / `export_state`.
- [x] 1.6 Remove the now-unused `LoadCardsAction` import.

## 2. Tests

- [x] 2.1 Prove `load_prebuilt_deck` emits exactly one event with the resulting
      state and the replayable raw `LOAD_CARDS` action args.
- [x] 2.2 Prove `load_state` emits exactly one state-only event.
- [x] 2.3 Prove `reset_game` emits exactly one state-only event.
- [x] 2.4 Prove an emission failure does not break any of the three operations.
- [x] 2.5 Update the restore test to expect the snapshot load to emit a state event.

## 3. Verification

- [x] 3.1 `uv run pytest tests/unit` passes (game-service).
- [x] 3.2 `./scripts/lint.sh --fix` clean.
- [x] 3.3 Sync `openspec/specs/game-service/spec.md` after implementation.
