# Tasks

## 1. Pure rule — `runtime/seat_turn_guard.py`

- [x] 1.1 Define the phase classification from the simplified state's `stepId`
      (player `1.1`/`1.2`, villain `2.1`-`2.5`, beginning `0.0`, end `0.1`,
      unknown) with the player phase as the only phase where a seat may act.
- [x] 1.2 Define `PHASE_ADVANCING_TOOLS` (`next_step`, `prev_step`,
      `player_end_phase`, `villain_end_phase`) and `SEAT_ACTION_TOOLS` (the
      game-mutating tools a seat plays with), excluding `mulligan_draw_hand` and
      the lifecycle/read-only tools.
- [x] 1.3 Implement `check_turn_authority(caller_player_id, tool_name, step_id)`
      returning a `TurnAuthorityViolation` (kind `phase_advance` or `action`,
      with the phase and a corrective `message`/`required_undo`) or `None`.
      Unknown or missing `stepId` never fires. Pure: no repository, no I/O.

## 2. Detection at the call site — `runtime/prompt_run.py`

- [x] 2.1 Wire the detection into the tool-call loop beside the seat-scope check:
      seat jobs only, game-service tools only, phase-sensitive tools only.
- [x] 2.2 Resolve the game id via `_session_game_id` (the existing
      `metadata.game_id` mechanism) and read the current step by calling the
      session's own `get_game_state` tool through `McpToolCatalog.call_tool`
      with `ignore_failures=True`.
- [x] 2.3 On a violation, record a finding through the DRA-30 store the way
      `report_illegal_action` does: `repository.open_illegal_action` on the
      orchestrating session, then `_announce_illegal_action_finding` (durable
      event, live copy under the durable id, `illegal_action` history emission)
      on the orchestrating job.
- [x] 2.4 The call is dispatched normally after detection — the finding is
      recorded, the play is not blocked.

## 3. Scope note — `runtime/seat_guard.py`

- [x] 3.1 Rewrite the "does not police turn or phase authority" bullet
      (lines 62-65) to name the new module as the enforcement of the
      orchestrator-side judgement, so the two modules read as one story.

## 4. Tests

- [x] 4.1 Pure-rule tests in `tests/unit/test_seat_turn_guard.py` covering the
      three ticket scenarios (a seat calling `next_step` during another seat's
      turn, `player_end_phase` out of turn, an action tool during the villain
      phase) and the negatives (player-phase action tool, read-only tool during
      the villain phase, unknown step id, orchestrating job not checked).
- [x] 4.2 Wiring tests through the real `PromptRunService` (mirroring
      `test_prompt_run.py`): a seat job calling `next_step` with the board in
      the villain phase opens a finding in the store, publishes
      `illegal_action_finding` live, and emits an `illegal_action` history
      event; a read-only call during the villain phase records nothing.

## 5. Surrounding files

- [x] 5.1 Update `skills/marvel-champions-play/SKILL.md` — the "Turn and phase
      authority" row now states that the runtime records an illegal-action
      finding after the fact, replacing "caught by the orchestrator reading game
      state, or not at all".
- [x] 5.2 Update `services/agent-orchestrator/README.md` — the illegal-actions
      section and the `illegal_action_finding` event entry note the automatic
      detection.
- [x] 5.3 Run `./scripts/lint.sh --fix`, the agent-orchestrator unit suite, and
      `openspec validate --all` (expect the single pre-existing
      `spec/typed-game-actions` failure).
- [x] 5.4 Archive the change with `openspec archive dra-62-turn-phase-authority
      --yes` and confirm the archive directory exists.
