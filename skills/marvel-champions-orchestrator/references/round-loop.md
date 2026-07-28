# Round Loop — Steps to Tools

**Referenced by:** SKILL.md | **Rules source:** `marvel-champions-rules-reference/resources/round-structure.md`

Every game-service tool below takes the `session_id` recorded at setup — either the session UUID
or the room slug (e.g. `lively-fog-1234`), both accepted everywhere. Player-scoped tools take
`player_n` (`player1`..`player4`); card-scoped tools take an `instance_id` from the board.

---

## Tool inventory

This is the authoritative tool list. Do not invent tool names outside it.

| Group           | Tools                                                                                                                            |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Session         | `create_game`, `attach_game`, `lookup_session_by_slug`, `list_games`, `delete_game`                                              |
| Discovery       | `list_actions`, `get_session_actions`, `get_game_state`                                                                          |
| Catalog / load  | `search_prebuilt_sets_marvel_champions`, `load_prebuilt_deck`, `search_cards_marvel_champions`, `load_cards`, `unload_cards`     |
| Phase control   | `next_step`, `prev_step`, `player_end_phase`, `villain_encounter_phase`, `villain_end_phase`                                     |
| Setup helpers   | `set_player_count_action`, `mulligan_draw_hand`, `multiple_double_sided_villains`, `shadows_of_the_past`                         |
| Cards           | `draw_card`, `move_card`, `exhaust_card`, `ready_card`, `flip_card`, `shuffle_into_deck`, `set_card_property`                    |
| Tokens          | `modify_tokens`, `zero_tokens`                                                                                                   |
| Encounter       | `deal_encounter`, `draw_boost`, `discard_minion`, `discard_side_scheme`                                                          |

**Discovering what the plugin accepts.** `list_actions` returns the generic action catalog;
`get_session_actions` returns the catalog *for a specific session*, including the plugin's load
groups and plugin metadata. Call `get_session_actions` once at setup (via a subagent — it is a large
payload) to confirm which phase tools and group ids the loaded plugin actually supports, rather than
assuming.

**Prefer typed phase tools.** Where `player_end_phase`, `villain_encounter_phase`, or
`villain_end_phase` exist, use them instead of hand-rolled `next_step` sequences. They run the
plugin's own automation for the whole phase step. Use `next_step` only to walk sub-steps the typed
tools do not cover, and `prev_step` only to back out of a mis-advance.

**Large payloads.** `get_game_state` and `search_cards_marvel_champions` must always be called from
inside a `spawn_subagent`, never directly in the orchestrator job.

---

## The ten round steps

| # | Round step (rules)               | Who acts       | Tools                                                                                   |
| - | -------------------------------- | -------------- | ----------------------------------------------------------------------------------------- |
| 1 | Player phase begins              | Orchestrator   | none — bookkeeping only; log round number and first player                              |
| 2 | Each player takes a turn         | **Player agent** per seat, orchestrator schedules | `prompt_player_agent` → `wait_for_subagent` per seat, in player order. The seat itself uses `move_card`, `exhaust_card`, `ready_card`, `flip_card`, `modify_tokens`, `draw_card`, `shuffle_into_deck`, `set_card_property` on its own cards |
| 3 | Player phase ends                | Orchestrator   | `player_end_phase` (discard to hand size, draw up, ready all). Optional extra discards are a seat decision |
| 4 | Villain phase begins             | Orchestrator   | implied by `player_end_phase`; verify with a delegated state read if uncertain           |
| 5 | Place threat on main scheme      | Orchestrator   | `modify_tokens` on the main scheme with `threat` = acceleration field + 1 per acceleration icon + 1 per acceleration token |
| 6 | Villain and minions activate     | Orchestrator, with **player decisions delegated** | `draw_boost` per villain activation; `flip_card` to reveal the boost; `modify_tokens` for damage or threat; `exhaust_card` for a defender; `ready_card`/`zero_tokens` as cleanup |
| 7 | Deal encounter cards             | Orchestrator   | `villain_encounter_phase` (deals facedown to all players), or `deal_encounter` per player plus one per hazard icon in player order |
| 8 | Reveal and resolve encounter     | Orchestrator, with **player decisions delegated** | `flip_card` / `set_card_property` to reveal; `move_card` to place by card type; `modify_tokens` for starting threat; `shadows_of_the_past`, `discard_minion`, `discard_side_scheme` for the named encounter effects |
| 9 | Pass the first player token      | Orchestrator   | bookkeeping; `villain_end_phase` closes the phase and returns to the player phase        |
| 10| End the round                    | Orchestrator   | emit the round summary, check win/loss, increment round, return to step 1                |

---

## Step 6 in detail — activations

For each player, in player order:

1. **Villain activates against that seat.**
   - `draw_boost(player_n=<seat>)` — every villain activation gets one boost card.
   - `flip_card` the boost to reveal it. Each boost icon is +1 ATK or +1 SCH for this activation; a
     star icon triggers the boost ability instead of granting +1.
   - Seat in **hero form** → attack. Ask the seat whether to defend **before** the boost is flipped
     (see `player-turn-prompt.md`, mid-villain-phase prompt). Apply DEF reduction, then
     `modify_tokens` damage onto the hero or the defending ally.
   - Seat in **alter-ego form** → scheme. `modify_tokens` threat onto the main scheme equal to the
     modified SCH.
2. **Each minion engaged with that seat activates**, one at a time, in that seat's chosen order.
   Minions get no boost card unless they have the villainous keyword. Same hero/alter-ego branch.
3. If an activating minion leaves play mid-activation, that activation ends immediately.

---

## Step 8 in detail — reveal by card type

| Card type    | Placement                                                    | Then                                             |
| ------------ | -------------------------------------------------------------- | ------------------------------------------------ |
| Minion       | `move_card` into the revealing seat's play area, engaged      | resolve When Revealed                            |
| Treachery    | resolve, then discard — never enters play                     | resolve When Revealed, then discard              |
| Attachment   | `move_card` attached to the specified element (usually villain) | resolve When Revealed                          |
| Side scheme  | `move_card` into the villain area; `modify_tokens` starting threat | resolve When Revealed; note crisis/acceleration/hazard icons |
| Environment  | `move_card` into the villain area                             | resolve When Revealed                            |
| Obligation   | goes to the indicated player's area                           | **that seat resolves it** — delegate the decision |

- **Surge** — the revealing seat immediately reveals one additional encounter card.
- A revealed card whose ability specifies "Hero" or "Alter-Ego" resolves only if the **revealing
  player** is in that form.
- Any choice that belongs to the revealing player is delegated to that seat. Any choice the rules
  assign to "the first player" is delegated to the first player's seat.

---

## Deck-empty rules to watch for

These fire mid-loop and are easy to miss. Watch for them on every draw, boost, and deal.

| Situation                                                         | Required handling                                                                                          |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Encounter deck empties                                            | Immediately shuffle the encounter discard pile into a new encounter deck **and place 1 acceleration token** next to the main scheme deck. That token adds +1 threat every subsequent step 5 — record it in the round log. |
| Encounter deck **and** encounter discard both empty at once       | Infinite acceleration tokens → **players lose**. Terminal condition; stop the loop.                        |
| A card ability discards from the encounter deck and it empties mid-effect | The ability is considered fulfilled. Do **not** keep discarding from the newly shuffled deck.      |
| A player deck empties                                             | Shuffle that player's discard pile into a new deck, then **immediately deal that player 1 facedown encounter card** (`deal_encounter` with `facedown=true`). |
| A player deck empties and that player's discard is also empty     | The deck does not reset until at least 1 card enters the discard pile; then deal the facedown encounter card. |

Accumulated acceleration tokens are orchestrator bookkeeping. Carry the count in the round log.

---

## Setup call order

| Order | Tool                                        | Notes                                                                              |
| ----- | ------------------------------------------- | ---------------------------------------------------------------------------------- |
| 1     | `create_game`                               | returns `session_id` — required by every later call                                |
| 2     | `get_session_actions`                       | via subagent; confirms plugin action catalog and load group ids                    |
| 3     | `set_player_count_action`                   | must equal the roster size from `list_player_agents()`                             |
| 4     | `search_prebuilt_sets_marvel_champions`     | via subagent; return `{name, deck_id}` pairs only                                  |
| 5     | `load_prebuilt_deck`                        | one call per hero deck, one for the villain/scenario set                           |
| 6     | `multiple_double_sided_villains`            | only if the scenario uses multiple double-sided villains                           |
| 7     | `mulligan_draw_hand`                        | once per player                                                                    |
| 8     | delegated state read                        | confirm hands, villain HP, main scheme target before round 1                       |

`attach_game` and `lookup_session_by_slug` are for resuming an existing DragnCards room rather than
creating one (`lookup_session_by_slug` only reads metadata — a slug already works as `session_id`);
`list_games` and `delete_game` are session housekeeping and are not part of the loop.
