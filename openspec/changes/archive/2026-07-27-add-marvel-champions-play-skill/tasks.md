## 1. Ground the Skill in the Real Harness

- [x] 1.1 Read the typed action models in `services/game-service/src/game_service/logic/actions.py` and record the DragnLang each action emits
- [x] 1.2 Read `services/game-service/src/game_service/api/routers/game_action_helpers.py` and record the per-action MCP tool names and summaries
- [x] 1.3 Read `_simplify_marvel_state` in `services/game-service/src/game_service/api/routers/game_state.py` and record every field the agent can and cannot see
- [x] 1.4 Extract the canonical Marvel Champions group ID list and the plugin `groups.json` `onCardEnter` semantics
- [x] 1.5 Extract the plugin `steps.json` step order and the `playerEndPhase` / `villainEndPhase` / `drawBoost` action lists
- [x] 1.6 Confirm how skills are surfaced to a session agent (`load_skill`, `load_skill_reference`, `game-service_` tool-name prefix, no filesystem access)

## 2. Live Verification Against a Running Stack

- [x] 2.1 Create a throwaway Marvel Champions session and load a hero, villain, and modular set
- [x] 2.2 Verify `mulligan_draw_hand` draws up to hand size and does not discard excess cards
- [x] 2.3 Verify the pay-cost-then-play sequence (`move_card` to `playerNDiscard`, then `move_card` to a play group)
- [x] 2.4 Verify `flip_card` toggles identity side A (hero) / side B (alter-ego) and that `handSize` tracks the form
- [x] 2.5 Verify `exhaust_card`, `ready_card`, `modify_tokens`, and `zero_tokens` against the resulting state
- [x] 2.6 Verify that `hitPoints` and `villainHitPoints` are maxima and that damage lives in card tokens
- [x] 2.7 Verify `prev_step` moves only the step marker and does not undo card moves or tokens
- [x] 2.8 Verify `deal_encounter` and `draw_boost` destinations and how boost cards appear in the simplified state
- [x] 2.9 Verify `shuffle_into_deck` failure and record the `error` payload verbatim
- [x] 2.10 Delete the throwaway session

## 3. Write the Skill

- [x] 3.1 Create `skills/marvel-champions-play/SKILL.md` with frontmatter matching the minimal parser (flat keys, one nesting level, single-line description)
- [x] 3.2 Write the turn decision loop and the resource-file routing table into `SKILL.md`
- [x] 3.3 Write `resources/reading-state.md` mapping simplified state fields and zones to game concepts
- [x] 3.4 Write `resources/tool-reference.md` covering every player-relevant tool, its arguments, its real effect, and the forbidden list
- [x] 3.5 Write `resources/play-recipes.md` with ordered tool-call sequences for the common plays
- [x] 3.6 Write `resources/strategy.md` tying prioritisation heuristics to observable state
- [x] 3.7 Write `resources/recovery.md` covering verification, the `error` contract, and corrective sequences

## 4. Specs and Verification

- [x] 4.1 Add `openspec/changes/2026-07-27-add-marvel-champions-play-skill/specs/marvel-champions-play-skill/spec.md`
- [x] 4.2 Sync the change into `openspec/specs/marvel-champions-play-skill/spec.md`
- [x] 4.3 Run `./scripts/lint.sh --fix`
- [x] 4.4 Run `./scripts/test.sh unit`
