---
name: marvel-champions-play
description: Play one Marvel Champions hero well through the real game-service tool surface - read the simplified state, decide a turn, and execute plays as concrete tool calls.
metadata:
  game: "Marvel Champions: The Card Game"
  role: "player"
  scope: "single hero, single turn"
  version: "1.0"
---

You control **one hero** in a Marvel Champions game running on DragnCards, driven through
the `game-service` MCP tools. Something else — a human or a coordinating agent — tells you
when it is your turn and when it is over. Your job is to take that turn well and stop.

This skill is about **execution**, not rules recitation. It tells you what the tools
actually do, which is frequently not what their one-line summaries say. Where this skill
and a tool summary disagree, this skill is right — every claim here was checked against a
live game.

For rules questions (keyword text, timing windows, card interactions) load the
`marvel-champions-rules-reference` skill instead. This skill assumes you know the rules
and need to know how to *perform* them here.

---

## First: what you are and are not allowed to do

**You do:** read state, flip your identity, play your cards, pay their costs, use basic
powers and card abilities, attack and thwart and defend, apply damage and threat, and
report what you did.

**You never do** (these belong to the coordinator or the human):

| Never call | Why |
| --- | --- |
| `player_end_phase` | Readies **and redraws for every player**, adds acceleration threat, jumps to the villain phase. Catastrophic mid-turn. |
| `villain_encounter_phase`, `villain_end_phase` | Global phase automation; `villain_end_phase` increments the round and rotates the first player. |
| `next_step`, `prev_step` | Move the shared step marker for the whole table. |
| `deal_encounter`, `draw_boost` | Villain-phase automation. |
| `discard_minion`, `discard_side_scheme`, `shadows_of_the_past`, `multiple_double_sided_villains` | Setup / encounter automation. |
| `create_game`, `attach_game`, `delete_game`, `load_prebuilt_deck`, `load_cards`, `unload_cards`, `set_player_count_action` | Session and setup lifecycle. |
| `raw_action` | Unvalidated DragnLang. Not needed for play; a typo corrupts the table. |
| Anything targeting another player's `playerN*` group | Not yours. Even `modify_tokens` on their ally. |
| Anything targeting `sharedEncounterDeck`, `sharedVillainDeck`, `sharedMainSchemeDeck` | You do not manipulate the villain's decks. |

You *may* read the whole board, including other players' zones. Reading is always safe.

---

## The turn loop

Run this every time you are told it is your turn.

**1. Read.** Call `get_game_state(session_id)`. Establish, before anything else:

- Which player you are (`player1`..`player4`). If you were not told, ask — do **not** guess.
- Your form: the card in `playerNPlay1` whose `instanceId` starts with your hero's slug.
  `currentSide: "A"` = hero, `currentSide: "B"` = alter-ego.
- Your remaining HP = `players.<you>.hitPoints` − that card's `tokens.damage`.
- Threat on the main scheme = `sharedMainScheme[0].tokens.threat`.
- Villain remaining HP = `villainHitPoints` − `sharedVillain[0].tokens.damage`.
- What is in `playerNEngaged` (minions and side schemes on you) and `playerNPlay2` (your board).
- Your hand: the cards in `playerNHand`.

Load `resources/reading-state.md` the first time you do this, or whenever a field surprises you.

**2. Price your hand.** The state gives you card *names* only — no costs, no icons, no
text. Call `search_cards_marvel_champions(name=...)` for each unfamiliar card and match on
`database_id` == the state card's `id`. Read `cost`, `resource`, `attack`, `thwart`,
`defense`, `health`, `rules`. Do this once per card name and remember it for the session.

**3. Choose your form.** Hero form lets you attack, thwart, and defend. Alter-ego form
lets you recover and use alter-ego abilities, but the villain will attack you. Load
`resources/strategy.md` for the decision heuristic. Changing form costs your whole turn's
tempo — you cannot act meaningfully in the form you left.

**4. Sequence your plays.** Cheap board development before expensive one-shots; play
allies before you need them; keep enough cards in hand to pay for the event you want to
land. Every play is: pay the cost by discarding resources, then move the card into play.
Load `resources/play-recipes.md` for the exact call sequences.

**5. Use your basic power once.** Exhausting your hero for a basic attack or basic thwart
is free value. Do not end a hero turn with an unexhausted hero unless you are deliberately
holding it for a defense.

**6. Verify.** After each mutating call, check the `error` field of the response. After a
group of related calls, re-read state and confirm the board looks the way you intended.

**7. Stop and report.** Say what you did, what the board looks like now, and hand control
back. Do **not** advance the phase. Do **not** draw back up to hand size — the coordinator's
end-of-phase step does that for everyone at once.

---

## Ten harness facts that will otherwise bite you

1. **`success` is always `true`.** Every action returns `{"session_id": ..., "success": true, "error": ...}`.
   The *only* failure signal is a non-null `error` string. Read it every time.
2. **`players.<you>.hitPoints` is your MAXIMUM HP**, not your remaining HP. Damage is
   `tokens.damage` on your identity card.
3. **`players.<you>.handSize` is your target hand size for your current form**, not how
   many cards you hold. It changes when you flip. Count `playerNHand` for the real number.
4. **`villainHitPoints` is the current stage's total HP**, already scaled for player count.
   Remaining = that minus `tokens.damage` on the `sharedVillain` card.
5. **`tokens` is sparse.** A missing key means zero. Never assume the key exists.
6. **`HIDDEN` entries are merged placeholders.** Their `instanceId` is inherited from the
   first stack in the group and does **not** identify the hidden card. Never target one.
7. **Nothing validates costs.** You move resource cards to your discard yourself. If you
   forget, the game happily lets you play a 4-cost card for free — and you have cheated.
8. **`prev_step` is not undo.** It moves the step marker only. Card moves, tokens, and
   exhaustion are permanent; fix mistakes with inverse actions.
9. **`mulligan_draw_hand` draws *up to* hand size and never discards** — despite its tool
   summary claiming otherwise. If your hand is already at or above hand size it does nothing.
10. **`shuffle_into_deck` is currently broken.** It returns
    `error: "... Group not found: cardById<id>deckGroupId ..."` and does nothing. Use
    `move_card` to `playerNDeck` instead.

---

## Tool names

Inside an agent session the game-service tools are exposed with the registry name
prefixed: `game-service_get_game_state`, `game-service_move_card`, and so on. This skill
writes the bare names (`get_game_state`, `move_card`). Use whichever form your tool list
shows. Every tool takes `session_id` as its first argument — the UUID, never the room slug.

---

## Reference files

| File | Load when... |
| --- | --- |
| [resources/reading-state.md](resources/reading-state.md) | You are reading the board and need the full field-by-field and zone-by-zone map, including what the state does *not* tell you. |
| [resources/tool-reference.md](resources/tool-reference.md) | You need the exact arguments and real behaviour of a tool, or need to check whether a tool is allowed. |
| [resources/play-recipes.md](resources/play-recipes.md) | You are about to execute a play and want the exact ordered call sequence. |
| [resources/strategy.md](resources/strategy.md) | You are choosing between thwart and attack, deciding whether to flip, or planning a resource curve. |
| [resources/recovery.md](resources/recovery.md) | An action returned an `error`, the board does not match your intent, or you need to undo something. |

Start with `resources/play-recipes.md` if you are mid-turn and just need to act.
