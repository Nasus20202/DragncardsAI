# Tool reference

Every tool takes `session_id` (the session **UUID**, never the room slug) plus the
arguments listed. In an agent session the names are prefixed with the MCP registry name:
`game-service_move_card`, etc.

Every mutating tool returns:

```json
{ "session_id": "...", "success": true, "error": null }
```

`success` is hard-coded `true`. **`error` is the only failure signal.** It is populated
when the underlying DragnLang logged an `ABORT:` or an
`Error in Marvel Champions triggered by [...]` message. It is cleared before each action,
so it never goes stale.

---

## Tools you use constantly

### `get_game_state(session_id)`

Returns the simplified state. See `resources/reading-state.md`. Safe, cheap, idempotent.
Call it liberally.

### `move_card(session_id, instance_id, dest_group_id, dest_stack_index=-1, dest_card_index=0, player_n=null)`

The workhorse. Emits `["MOVE_CARD", instanceId, destGroupId, destStackIndex]`.

- `dest_stack_index`: `-1` appends to the end of the group. Use `-1` for play areas and
  discards. Use `0` to place on top of a deck.
- `dest_card_index`: `0` puts the card on top of the destination stack. Non-zero values
  tuck it under — this is how attachments and upgrades get stacked onto a card.
- `player_n`: set it to your own player id whenever the source or destination is one of
  your groups. It injects `player_ui.playerN` so plugin automation that references
  `$PLAYER_N` fires correctly. If omitted, the service infers it from a `playerN`-prefixed
  destination group, but setting it explicitly is safer.
- The destination group's `onCardEnter` rewrites the card's side: decks → facedown,
  everything else → faceup.

`dest_group_id` must be one of the concrete group ids (`player1Hand`, not `playerNHand`).

### `exhaust_card(session_id, instance_id)` / `ready_card(session_id, instance_id)`

Emit `["EXHAUST_CARD", id]` / `["READY_CARD", id]`. Set rotation 90 / 0, which surfaces as
`exhausted: true` / `false`. Idempotent in practice — exhausting an exhausted card is a
no-op, not an error.

### `modify_tokens(session_id, instance_id, token_type, amount)`

Emits `["INCREASE_VAL", "/cardById/<id>/tokens/<type>", amount]`. `amount` may be negative.

`token_type` must be one of: `damage`, `threat`, `generic`, `acceleration`, `confused`,
`stunned`, `tough`.

This is how **all** damage, threat, and status changes happen. There is no separate
"deal damage" or "remove threat" tool. Nothing clamps the value — you can drive tokens
negative if you subtract too much, so read state first.

Meaning by target:

| Target | `damage` | `threat` |
| --- | --- | --- |
| Your identity card | Damage on you | Threat placed on you by effects |
| `sharedVillain` card | Damage on the villain's current stage | — |
| `sharedMainScheme` card | — | Threat on the main scheme |
| A side scheme in `playerNEngaged` | — | Threat on that side scheme |
| A minion in `playerNEngaged` | Damage on the minion | — |
| An ally in `playerNPlay2` | Damage on the ally | — |

`tough`, `stunned`, and `confused` are status counters; set them to `1` to apply the
status and `-1` to strip it.

### `zero_tokens(session_id, instance_id)`

Emits `["SET", "/cardById/<id>/tokens", {}]`. Wipes **all** tokens on the card, including
statuses. Use for full heals and for defeated-enemy cleanup, not for partial removal.

### `flip_card(session_id, instance_id)`

Cycles `A → B → A` (or `A → B → C → A` if the card has a C side). For an identity card,
side **A is the hero** and side **B is the alter-ego**. Games start with identities on
side B (alter-ego), matching the setup rule.

Flipping your identity changes which `handSize` the state reports, but **does not** change
your hand, ready cards, or tokens.

### `draw_card(session_id, player_n, count=1)`

Emits `["DRAW_CARD", count]` with `player_n` context. Draws exactly `count` cards from
`playerNDeck` to `playerNHand`. Use this only when a card effect says "draw N cards".
`player_n` accepts `player1`..`player4` (and `shared`, which you will never want).

### `search_cards_marvel_champions(name=, type_code=, classification=, official_only=true, limit=50)`

Not session-scoped — no `session_id`. Substring match on `name`, exact match on
`type_code`, substring on `classification`. Returns `{total, cards:[{database_id, name,
subname, type_code, classification, traits, official, attributes:{...}}]}`.

Match the state card's `id` against `database_id` to get the exact printing. Multiple
printings of the same card share a name and stats but have different `database_id`s.

---

## Tools you use rarely

### `mulligan_draw_hand(session_id, player_n)`

The underlying action list is just `DRAW_HAND`: it draws **up to** the player's current
hand size and **discards nothing**. If your hand is already at or above hand size it is a
no-op.

Use it only at setup, after you have manually discarded the cards you want to mulligan
(`move_card` each to `playerNDiscard` first). During a normal turn, leave hand refills to
the coordinator's end-of-phase step.

### `set_card_property(session_id, instance_id, property_path, value)`

Low-level `["SET", "/cardById/<id>/<path>", value]`. Prefer `flip_card`, `exhaust_card`,
`ready_card`, and `modify_tokens` — they exist so you do not need this. Legitimate use is
narrow, e.g. forcing `currentSide` to a specific value rather than cycling.

### `shuffle_into_deck(session_id, instance_id)` — **BROKEN**

Currently fails. It builds a malformed DragnLang path and returns, verbatim:

```
Error in Marvel Champions triggered by [player1/player1]: Group not found:
cardById<instanceId>deckGroupId Trace: ["Shuffle card <instanceId> into its deck", "index 1"]
```

The card does not move. **Workaround:** `move_card(instance_id, "playerNDeck", dest_stack_index=0)`
puts it facedown on top of your deck. That is not a shuffle — if the effect genuinely
requires shuffling, say so in your report and let the coordinator or human handle it.

---

## Tools that are not yours

Calling any of these as a player agent will corrupt the shared game. They are listed here
so you recognise them and refuse.

| Tool | What it actually does |
| --- | --- |
| `player_end_phase` | Runs `READY_ALL` + `DRAW_HAND` for **every** player in turn order, computes and applies acceleration threat to the main scheme, then sets `stepId` to `2.1`. |
| `villain_encounter_phase` | Sets `stepId` to `2.3` and deals a facedown encounter card to every player. |
| `villain_end_phase` | Rotates the first player token, sets `stepId` to `1.1`, and increments `roundNumber`. |
| `next_step` / `prev_step` | Move the shared step marker along `0.0, 1.1, 1.2, 2.1, 2.2, 2.3, 2.4, 2.5, 0.1`. `prev_step` is **not** an undo. |
| `deal_encounter` | Deals an encounter card to a player; the card lands in that player's `playerNEngaged`. |
| `draw_boost` | Moves the top encounter card into `playerNEngaged` at rotation -30 with `boost: true`, reshuffling the discard into the deck first if needed. |
| `discard_minion` / `discard_side_scheme` | Mill the encounter deck until a minion / side scheme is found. |
| `shadows_of_the_past` | Puts a player's nemesis set into play. |
| `multiple_double_sided_villains` | Scenario setup. |
| `create_game`, `attach_game`, `delete_game` | Session lifecycle. |
| `load_prebuilt_deck`, `load_cards`, `unload_cards` | Deck and card loading. |
| `set_player_count_action` | Sets `numPlayers` and the table layout. |
| `raw_action` | Arbitrary DragnLang. No guardrails at all. |
| `get_session_actions` | Read-only but enormous — dumps every plugin action list into your context. |

Also off limits by target rather than by tool: **any** action whose `instance_id` belongs
to a card in another player's `playerN*` group, or to a card in `sharedEncounterDeck`,
`sharedVillainDeck`, or `sharedMainSchemeDeck`.
