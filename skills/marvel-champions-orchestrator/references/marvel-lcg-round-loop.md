# marvel-lcg round loop

Load only for a `marvel-lcg` session. This engine adjudicates rules, asks named seats for
decisions, and advances turns as part of accepted options. The coordinator observes and
schedules; it may call `list_game_options` only to obtain the authoritative current engine prompt
for delegation. It must not choose an option or call `choose_game_option` on behalf of the player,
and does not synthesize a phase-advancing call. The seat agent calls `list_game_options` and
`choose_game_option` to take actions.
## Setup order

1. Call `game-service_list_game_setup_catalog` with
   `{"platform":"marvel-lcg"}` and retain opaque `scenario.id` and
   `hero_decks[].id` values. Do not construct engine paths or choose the first
   catalog entry.
2. Call `game-service_create_game` with
   `{"platform":"marvel-lcg","setup":{"platform":"marvel-lcg",
   "scenario_id":<id>,"hero_decks":[{"seat":"player1",
   "hero_deck_id":<id>}, ...]}}`. Preserve the exact contiguous roster order
   and stop if a requested id is absent.
3. Read the returned session metadata and verify its `platform`, `move_surface`, and
   echoed `setup` before reading the initial neutral state.
4. Prompt only after `pendingSeats` names a seat and load the play skill's
   `references/marvel-lcg.md` in that seat.

The engine's setup prompts, mulligans, and form changes are options. Do not call
DragnCards typed actions, load groups, or phase helpers for this platform.

## Prompt loop

Repeat until the normalized state reports `mode=win`, `mode=loss`, or a service failure:

1. Read `get_game_state` for the game and retain the complete normalized state checkpoint.
   Treat `playRound`, `phase`, `mode`, `players`, `zones`, and a present `pendingSeats` list
   as authoritative. Treat `phaseLabel` as opaque. If a required value is missing or
   contradictory, perform one fresh state read and then stop if it is not resolved.
2. If `pendingSeats` names a seat, prompt exactly that seat using
   `references/player-turn-prompt.md`. The coordinator may read `list_game_options` to copy
   the exact current engine response but never chooses from it. The prompt must carry the
   latest verified normalized state and that exact response; the coordinator does not
   synthesize rules, card statistics, outcomes, or a preferred choice. If no seat is pending,
   wait for the next state rather than inventing a turn transition.
3. The seat agent reads `list_game_options` for its assigned seat, chooses by stable
   `option_id`, and submits exactly once with `choose_game_option`, including the resolved
   targets, payments, `prompt_id`, and `prompt_version` returned by the options read. It
   reports the selected option and result to the coordinator.
4. Wait for the seat report, then verify that the prompt changed or the seat left
   `pendingSeats`; a response status alone is not confirmation. Re-read normalized state
   before accepting any result or terminal claim.
5. If the identical prompt and option ids recur, record the rejected choice, do not send it
   again, and ask the seat to choose another legal option or report the stuck state.
6. Update the compact round log from the new normalized checkpoint and continue.

Ending a turn is an engine-owned option, not a coordinator call. The engine enforces turn
order, phase transitions, costs, legal targets, and the once-per-turn form rule. A seat acting
while absent from `pendingSeats` is still recorded as an illegal-action finding because the
engine may silently discard that submission.
