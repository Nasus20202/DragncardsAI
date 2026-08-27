# DragnCards round loop

Load only for a `dragncards` session. The game-service is a composing playtable, so the
coordinator owns phase transitions and villain automation.

## Tool inventory

All calls take the game `session_id`; player-scoped calls use `player_n` and card calls
use an `instance_id` copied from the neutral state.

- Session: `create_game`, `attach_game`, `lookup_session_by_slug`, `list_games`,
  `delete_game`.
- Discovery: `get_session_actions`, `get_game_state`, `list_actions`.
- Setup: `set_player_count_action`, `search_prebuilt_sets_marvel_champions`,
  `load_prebuilt_deck`, `mulligan_draw_hand`, and scenario-specific setup helpers.
- Player calls delegated to seats: `move_card`, `exhaust_card`, `ready_card`,
  `flip_card`, `shuffle_into_deck`, `draw_card`, `set_card_property`,
  `modify_tokens`, `zero_tokens`.
- Coordinator phase and encounter calls: `player_end_phase`, `villain_encounter_phase`,
  `villain_end_phase`, `next_step`, `prev_step`, `deal_encounter`, `draw_boost`,
  `discard_minion`, `discard_side_scheme`, and scenario automation.

## Setup order

1. Create or attach the game and retain its session id.
2. Read the session action catalog through a subagent.
3. Set the player count to the validated roster size.
4. Resolve hero and scenario set ids by name; never hardcode UUIDs.
5. Load one hero deck per seat, then the villain/scenario set.
6. Mulligan each seat and delegate a state read confirming the deck, hand, and hero.
7. Read neutral state after setup. Record `playRound`, `stepId`, `phase`, `phaseLabel`,
   and the first player.
8. If the state is `stepId == "0.0"` and `phase == "passive"` (Beginning of Round),
   the coordinator must call `next_step` once. Do not prompt a seat while the phase is
   `passive`.
9. Re-read neutral state and require `phase == "player"` before scheduling a seat. If
   the expected player phase is not observed, stop and report the observed state; do not
   prompt a seat and do not infer success from the `next_step` response.
10. Prompt the first seat only after the player-phase checkpoint succeeds.

## Round order

1. Re-read neutral state at the start of each player phase. Stop immediately if the
   game is terminal.
2. Record the observed `playRound` and first player. If the state is the DragnCards
   Beginning-of-Round checkpoint (`stepId == "0.0"` and `phase == "passive"`), the
   coordinator must call `next_step` once.
3. Re-read neutral state and require `phase == "player"` before prompting any seat.
   If the expected player phase is not observed, stop and report the observed state.
   Do not prompt a seat while the phase is `passive` or `villain`.
4. Prompt every non-defeated seat in player order; wait for and verify each report.
5. Run `player_end_phase` once after every seat reports.
6. Resolve the villain phase: acceleration threat, villain/minion activations with
   delegated seat decisions, encounter dealing, and encounter resolution.
7. Pass the first-player marker and run `villain_end_phase`.
8. Re-read state, check terminal conditions, and begin the next `playRound`, applying the
   player-phase checkpoint before scheduling its first seat.

The coordinator must not pay a hero's costs or choose a hero's attack, thwart, defense,
or form change. A seat's player-phase action may be composed, but its report and the
resulting neutral state are the evidence used for evaluation.
