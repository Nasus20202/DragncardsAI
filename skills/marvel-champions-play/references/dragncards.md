# DragnCards harness reference

Load this file only when the session platform is `dragncards`. It is the authoritative
description of the DragnCards game-service move surface. The platform is a playtable: it
accepts composed actions and does not adjudicate Marvel Champions rules.

## State and zones

`get_game_state(session_id)` returns the simplified state. DragnCards' `roundNumber` is
the completed-round counter; use the neutral state's `playRound` instead. Its `stepId`
and `stepDescription` are meaningful only on this platform. `players.<seat>.hitPoints`
is maximum health, `handSize` is the current form's target hand size, and
`villainHitPoints` is the current stage's total. Derive remaining values by subtracting
the relevant `damage` token.

Concrete zone identifiers are:

| Zone | Contents |
| --- | --- |
| `playerNHand` | The seat's hand |
| `playerNDeck` | The seat's facedown deck |
| `playerNDiscard` | The seat's face-up discard |
| `playerNPlay1` | The seat's identity |
| `playerNPlay2` | The seat's allies, upgrades, and supports |
| `playerNEngaged` | Enemies engaged with the seat, its side schemes, and facedown boosts |
| `playerNEvent` | An event resolving for the seat |
| `sharedVillain` | The current villain stage |
| `sharedMainScheme` | The main scheme |
| `sharedEncounterDeck` / `sharedEncounterDiscard` | Shared encounter cards |

`playerNEngaged` is not owned exclusively by the seat: it can contain shared encounter
cards, but the seat is the decision owner for effects assigned to it. Shared and villain
areas are valid targets when a rule assigns them to the acting seat. Moving a card into a
deck turns it facedown; moving it into hand, discard, or play turns it faceup.

Card entries are sparse. Missing `currentSide`, `exhausted`, and token keys mean their
defaults. A `HIDDEN` entry has no usable card identifier and must never be targeted.
Always copy `instanceId` from the current state; never construct it.

## Tool surface

Inside an agent session the names carry the `game-service_` prefix. The bare names below
are the operation names:

- Observe: `get_game_state`.
- Cards: `move_card`, `exhaust_card`, `ready_card`, `flip_card`, `draw_card`,
  `shuffle_into_deck`, `set_card_property`.
- Counters: `modify_tokens`, `zero_tokens`.
- Setup and phase automation belong to the coordinator:
  `player_end_phase`, `villain_encounter_phase`, `villain_end_phase`, `next_step`,
  `prev_step`, `deal_encounter`, `draw_boost`, `discard_minion`,
  `discard_side_scheme`, `shadows_of_the_past`, and `multiple_double_sided_villains`.
- Lifecycle and loading belong to the coordinator: `create_game`, `attach_game`,
  `delete_game`, `set_player_count_action`, `load_prebuilt_deck`, `load_cards`,
  `unload_cards`, and `mulligan_draw_hand`.

The mutating response has `success: true` even when the underlying action failed. The
only failure signal is a non-null `error`; read it after every call. The service clears
that field before each action. A failure can occur partway through a composed action, so
re-read state before attempting a repair. `raw_action` is not a player tool.

## Ordered recipes

For every recipe, copy the card's `instanceId`, pass your own `player_n` when a call
touches one of your zones, and verify the state after each stage.

### Pay and play

There is no cost enforcement. For each resource, move a card from `playerNHand` to
`playerNDiscard`, then move the played card to `playerNPlay2` (or `playerNEvent` while
an event resolves). Apply the card's text with the typed token, draw, and card tools.
Move a resolved event to `playerNDiscard`. A missed cost is cheating, not an error.

### Basic attack

`exhaust_card` the ready hero or ally, then `modify_tokens` on the legal target's
`damage`. Use the catalog attack value and clamp status effects yourself. Check the
villain's or minion's remaining health after the change; stage advancement is the
coordinator's job.

### Basic thwart

Exhaust the ready hero or ally, then reduce the chosen scheme's `threat` by no more than
the threat currently present. Move a defeated side scheme to the correct discard or
victory area.

### Defend, recover, and change form

During a villain decision, exhaust the chosen defender and apply reduced damage to it.
For an undefended attack, apply the full damage to the identity. In alter-ego form,
exhaust the identity and reduce its damage token by the recover value, never below zero.
Use `flip_card` to change form. The harness does not enforce the once-per-turn form limit.

### Repair and recovery

There is no undo operation. Repair an accidental move by moving the card back, repair a
token change with the opposite `modify_tokens`, and reapply individual tokens after an
accidental `zero_tokens`. `prev_step` only changes the shared step marker; it does not
undo a card action. If the board cannot be repaired with your own allowed tools, stop and
report the before and after observations.
