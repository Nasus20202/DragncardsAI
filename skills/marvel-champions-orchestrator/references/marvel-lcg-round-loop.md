# marvel-lcg round loop

Load only for a `marvel-lcg` session. This engine adjudicates rules, asks named seats for
decisions, and advances turns as part of accepted options. The coordinator observes and
schedules; it does not synthesize a phase-advancing call.

## Setup order

1. Create the game with `platform: marvel-lcg` and retain its session id.
2. Resolve one of the engine's scenario and hero-deck catalog entries.
3. Assign the roster's neutral seats and verify the initial neutral state.
4. Prompt only after `pendingSeats` names a seat and load the play skill's
   `references/marvel-lcg.md` in that seat.

The engine's setup prompts, mulligans, and form changes are options. Do not call
DragnCards typed actions, load groups, or phase helpers for this platform.

## Prompt loop

Repeat until the neutral state reports win, loss, or a service failure:

1. Read `get_game_state`; treat `playRound` as authoritative and `phaseLabel` as opaque.
2. If `pendingSeats` names a seat, prompt exactly that seat. The coordinator observes
   the pending set but does not call `list_game_options` or `choose_game_option` itself.
   If no seat is pending, wait for the next state rather than inventing a turn transition.
3. The seat agent calls `list_game_options`, chooses by stable `option_id`, and submits
   exactly once with `choose_game_option`, including the resolved targets and payments.
   It reports the selected option and result to the coordinator.
4. Wait for the seat report, then verify that the prompt changed or the seat left
   `pendingSeats`; a response status alone is not confirmation.
5. If the identical prompt and option ids recur, record the rejected choice, do not send
   it again, and ask the seat to choose another legal option or report the stuck state.
6. Re-read neutral state, update the compact round log, and continue.

Ending a turn is an enumerated option, not a coordinator call. The engine enforces turn
order, phase transitions, costs, legal targets, and the once-per-turn form rule. A seat
acting while absent from `pendingSeats` is still recorded as an illegal-action finding,
because the engine may silently discard that submission.
