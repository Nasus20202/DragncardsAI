# Tasks

## 1. Measure the reported problem

- [x] 1.1 Pull every recorded game from the running history-service: 29 games,
      the largest 122 events / **29.8 MB** (mean 245 KB per event).
- [x] 1.2 Break down one recorded `game_state` payload (470,263 chars): `deltas`
      224,807, `game.cardById` 165,446, `game.groupById` 22,870,
      `game.playerData` 14,764, plugin config (`functions`,
      `automationActionLists`, `ruleById`, `layout`) 27,485 — the board a judge
      needs is ~2,500.
- [x] 1.3 Confirm the failure mode: `_json` uses `sort_keys=True`, `deltas` sorts
      before `game`, so the 20,000-char clip of a 470 KB state is entirely delta
      log. Dumped a real move prompt (seq 76 of the 122-event game) and confirmed
      both state blocks end in `...[truncated 434002 chars of prior state]` with
      no board present.
- [x] 1.4 Baseline the prompt sizes with the real assembly code and
      `tiktoken`/`o200k_base` over 3 games (97 agent moves, 5 rounds, 3 games):
      move 13,750 mean tokens / 40,756 chars, round 1,505, game 268; total
      1,342,068 tokens; move assembly 7.3 ms mean.
- [x] 1.5 Confirm round/game roll-ups carry NO state: a round's closing seq is
      its last seq, usually an agent move, so `closing_state` is None.
- [x] 1.6 Count the recorded action distribution across all real games (97 agent
      moves) to size the skip opportunity: 31 non-strategic (14
      `search_prebuilt_sets_marvel_champions`, 12 `load_prebuilt_deck`, 3
      `set_player_count_action`, 1 `load_cards`, 1 `unload_cards`).
- [x] 1.7 Establish that `intended_action` is the MCP tool's own name
      (`tool_definition.actual_name`), and enumerate the authoritative tool
      surface from the running game-service OpenAPI operation ids.
- [x] 1.8 Confirm the judge cannot be driven end-to-end here: `GET /ready` reports
      `judge_configured: false` and the gateway container exposes no
      `EVAL_JUDGE_*_API_KEY`. Latency stays a projection, not a measurement.

## 2. Project the state

- [x] 2.1 Add `judge/state_view.py`: `project_state` reduces a raw DragnCards
      state to the `SimplifiedGameState` shape the game-service serves the
      playing agent; `render_state` projects then applies the char backstop.
- [x] 2.2 Collapse face-down cards and generic `player`/`encounter` backs to a
      `HIDDEN` count; describe only the top of a stack, with its size.
- [x] 2.3 Fall back to serialising an unrecognised state shape as recorded.
- [x] 2.4 Point `prompt.py` at `render_state` for move, round and game prompts.
- [x] 2.5 Fall back to the nearest recorded state for round and game closing
      states so a roll-up is never graded with no board.

## 3. Window the neighbouring actions

- [x] 3.1 Add `NeighbourMove` and `MoveInput.context_before/context_after`;
      `assemble_move_input` takes bounded `context_before`/`context_after`.
- [x] 3.2 Render both halves in the move prompt, labelling the following half as
      completion context and not hindsight to grade; clip each neighbour's
      reasoning.
- [x] 3.3 Add `EVAL_JUDGE_MOVE_CONTEXT_BEFORE` (8), `_AFTER` (3) and
      `_REASONING_CHARS` (400) with non-negative validation, and document the
      window rationale in `config.py`, `.env.example` and the README.

## 4. Classify and skip non-strategic actions

- [x] 4.1 Add `judge/actions.py` with the three-category taxonomy, the
      `mcp__server__tool` alias normalisation, and evaluate-by-default for every
      unrecognised name.
- [x] 4.2 Add `EVAL_SKIP_NON_STRATEGIC_MOVES` (true) and
      `EVAL_NON_STRATEGIC_ACTIONS` (defaulting to the built-in taxonomy, so the
      default is visible in configuration) plus the
      `Settings.non_strategic_actions` accessor.
- [x] 4.3 Skip in `Evaluator.evaluate_target` for move scope via the existing
      `Repository.mark_skipped`, with a reason naming the action and its category.
- [x] 4.4 Exclude non-strategic moves from round roll-ups and state the count in
      the prompt.

## 5. Tests

- [x] 5.1 `tests/unit/test_state_view.py` — delta log dropped and board kept;
      hidden information stays hidden; card shape; unoccupied seats and zero
      tokens omitted; unrecognised shape preserved; char backstop still bites.
- [x] 5.2 `tests/unit/test_actions.py` — the reporter's criterion (search skipped,
      draw/play evaluated); every strategic action evaluated; unrecognised names
      evaluated; alias normalisation; configured list replaces the default.
- [x] 5.3 `tests/unit/test_assembly.py` — window contents, defaults, edge
      clamping; round omits non-strategic moves and counts them; round closing
      state falls back.
- [x] 5.4 `tests/unit/test_judge.py` — window rendering and hindsight label;
      neighbour reasoning clipped; raw state projected in a move prompt; round
      prompt states the omitted count.
- [x] 5.5 `tests/unit/test_evaluator.py` — non-strategic move skipped with reason
      and no judge call; drawing still judged (over-skip guard); the toggle
      decides the outcome (parametrized both ways); round roll-up of only
      non-strategic moves still produced; configured window reaches the prompt.
- [x] 5.6 `tests/unit/test_config.py` — new defaults, overrides and validation.
- [x] 5.7 Verify every new test FAILS against the pre-fix `src`: 34 of 35 fail
      (two whole modules fail to import, the rest assert). The one that passes
      pre-fix is `test_taking_a_card_into_hand_is_still_judged`, a deliberate
      over-skip guard.

## 6. Re-measure and verify

- [x] 6.1 Re-run the same harness: move 3,067 mean tokens (−77.7%), prompts
      issued 66/97 (32.0% skipped), round 2,218, game 1,325, total 217,510
      (−83.8%), move assembly 0.5 ms (−93%).
- [x] 6.2 `uv run pytest tests/unit -q` — 178 passed (143 pre-existing, none
      regressed).
- [x] 6.3 `./scripts/lint.sh --fix` then `./scripts/lint.sh` — clean.
- [x] 6.4 Integration suite against the running Postgres.

## 7. Documentation and spec

- [x] 7.1 README: "What the judge is sent" and "Non-strategic actions are skipped,
      visibly", plus the configuration table rows.
- [x] 7.2 Service `AGENTS.md`: never prompt a raw recorded state; evaluate by
      default when classifying.
- [x] 7.3 Spec delta on `agent-move-evaluation`; sync `openspec/specs/`; archive;
      `openspec validate --all`.
