# Tasks

## 1. Tighten `_simplify_marvel_state` card output

- In `services/game-service/src/game_service/api/routers/game_state.py`,
  change `_simplify_marvel_state` so visible cards only emit `id`,
  `instanceId`, `name`, plus the non-default fields below. The
  function still returns a `SimplifiedGameState`, but it is built by
  passing a dict and using `model_dump(exclude_defaults=True)` so
  unset fields are not emitted.
  - Always emit: `id`, `instanceId`, `name`, `stackSize`.
  - Emit `currentSide` only when not `"A"`.
  - Emit `exhausted` only when `true`.
  - Emit `tokens` only when at least one counter is non-zero, with
    only the non-zero counters listed.
- Change the `HIDDEN` branch so a HIDDEN entry is just
  `{"name": "HIDDEN", "stackSize": N}`. Drop the placeholder `id`,
  `instanceId`, `currentSide`, `exhausted`, `tokens`.
- Make sure the returned shape is still a `SimplifiedGameState` so
  `GameStateResponse` and the other response models keep validating
  unchanged.
- Confirm the `roundNumber`, `mode`, `villainHitPoints`, `stepId`,
  `stepDescription`, `players` and `zones` keys are still emitted at
  the top level (they always are; the change is only inside `zones`).

## 2. Add a payload-size regression test

- In `services/game-service/tests/unit/test_game_state_api.py`, add a
  new test `test_simplify_marvel_state_payload_fits_mcp_limit` that
  builds a realistic worst-case raw state: 4 players with 40-card
  decks, the encounter deck, the villain, the main scheme, and
  attachments. Run it through `_simplify_marvel_state` and assert:
  - `len(json.dumps(result_dict, separators=(",", ":")).encode())`
    is under 256_000 bytes (well under the 1,048,576-byte limit).
  - Every visible card omits `tokens` when the card has no tokens.
  - Every HIDDEN entry is exactly `{"name": "HIDDEN", "stackSize": N}`.
- The fixture is small enough to ship inline (no real card database
  required): synthesize card names, UUIDs, stack ids, and a complete
  `cardById` / `groupById` / `playerData` tree with ~250 cards
  total.

## 3. Update the existing simplified-state unit tests

- In the same file, update the assertions on the existing tests
  (the ones that currently read `card["currentSide"] == "A"`,
  `card["exhausted"] is False`, `card["tokens"] == {}`, `card["id"]
  == "Unknown"`, etc.) so they accept either the old explicit-default
  shape or the new compact shape:
  - `currentSide` is `"A"` or absent; treat absent as `"A"`.
  - `exhausted` is `False` or absent; treat absent as `False`.
  - `tokens` is a dict, possibly empty, possibly missing; treat empty
    or missing as "no tokens".
  - For HIDDEN entries, the only required keys are `name` and
    `stackSize`; `id` and `instanceId` are no longer asserted.
- Add a small new test `test_simplify_marvel_state_hides_default_values`
  that pins the new compactness behaviour: a normal face-up card
  with all zero tokens emits only `id`, `instanceId`, `name`,
  `stackSize`.

## 4. Verify

- `cd wt-dra43/services/game-service && uv run pytest tests/unit/ -v`
  must pass. Report counts.
- `cd wt-dra43 && ./scripts/lint.sh --fix` (or `ruff` on the
  touched files if the full lint is too slow).
- `cd wt-dra43 && openspec validate --all` must report no new
  failures (one pre-existing `spec/typed-game-actions` failure is
  expected, and was already there before this change).

## 5. Archive

- After everything is green, run the OpenSpec archive flow to produce
  the dated archive folder under `openspec/changes/archive/`. Make
  sure every `TBD` / `TODO` / empty-section placeholder the generator
  left in the archived spec is replaced with real prose.
- Sync `openspec/specs/simplified-game-state/spec.md` to reflect the
  new compactness requirements. Update the existing scenarios where
  they assert specific field values, and add a new scenario for
  "simplified state omits default-valued card fields".
