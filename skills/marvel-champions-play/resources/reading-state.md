# Reading the board

`get_game_state(session_id)` returns a **simplified projection**, not the raw DragnCards
state. The raw state is deliberately not reachable over MCP. Everything below describes
what you actually receive.

## Top-level shape

```json
{
  "session_id": "c37cdc91-...",
  "state": {
    "roundNumber": 0,
    "mode": "standard",
    "villainHitPoints": 14,
    "stepId": "1.1",
    "stepDescription": "Player Turn",
    "players": { "player1": { "hitPoints": 10, "handSize": 5 } },
    "zones": { "<groupId>": [ <card>, ... ] }
  }
}
```

| Field | What it really means |
| --- | --- |
| `roundNumber` | Rounds completed. Starts at `0`; the villain-phase end step increments it. |
| `mode` | `"standard"`, `"expert"`, etc. Affects the encounter deck, not your tool usage. |
| `villainHitPoints` | **Total** hit points of the villain's *current stage*, already multiplied by player count. Not remaining HP. |
| `stepId` | Shared step marker. `0.0` beginning, `1.1` player turn, `1.2` end of player phase, `2.1`–`2.5` villain phase, `0.1` end of round. |
| `stepDescription` | Human-readable label for `stepId`. |
| `players.<playerN>.hitPoints` | **Maximum** hit points printed on that identity's current side. Never decreases from damage. |
| `players.<playerN>.handSize` | **Target** hand size for that identity's current side. Changes when the player flips. Not a count of held cards. |
| `zones` | Map of group id to the visible top card of each stack in that group. Groups with no cards are absent from the map entirely. |

A player only appears in `players` once they have an alias (a seated user). An absent
`playerN` key means that seat is empty.

## Card shape inside a zone

The card is **compact by default**: a face-up unexhausted card with no tokens looks like:

```json
{
  "id": "560cbe53-74a5-5338-bab9-5dbdb8cbfe02",
  "instanceId": "surveillanceteam_-h9iqbfj",
  "name": "Surveillance Team",
  "stackSize": 1
}
```

`currentSide`, `exhausted`, and `tokens` are **omitted** when they carry the default value
(`"A"`, `false`, and "all counters at zero" respectively). The same card with one damage
token and an exhaust looks like:

```json
{
  "id": "560cbe53-74a5-5338-bab9-5dbdb8cbfe02",
  "instanceId": "surveillanceteam_-h9iqbfj",
  "name": "Surveillance Team",
  "exhausted": true,
  "tokens": { "damage": 1 },
  "stackSize": 1
}
```

**Treat absent fields as their default.** `card.get("currentSide", "A")`,
`card.get("exhausted", False)`, `card.get("tokens", {}).get("damage", 0)`. Do **not** read
`card["currentSide"]` / `card.tokens["damage"]` directly — a quiet card with no `tokens`
key will throw.

| Field | Use |
| --- | --- |
| `id` | The catalog `database_id`. Feed this to card lookup to get cost/stats/text. |
| `instanceId` | **The handle for every action.** Format is `<slugified-name>_<suffix>`; readable, but never construct one — always copy it from state. |
| `name` | Name of the *currently visible side*. `"HIDDEN"` means a merged placeholder. |
| `currentSide` | `"A"` or `"B"` (a few cards have `"C"`). For identities: `A` = hero, `B` = alter-ego. **Absent on side A**; treat absence as `"A"`. |
| `exhausted` | `true` when the card is turned sideways and cannot act again this round. **Absent when ready**; treat absence as `false`. |
| `tokens` | **Sparse on two axes**: missing keys mean zero, and the whole field is absent when every counter is zero. Keys: `damage`, `threat`, `generic`, `acceleration`, `confused`, `stunned`, `tough`. |
| `stackSize` | Number of cards in this stack, including cards under the top one. For a deck this is the deck size. |

Only the **top card of each stack** appears. Attachments and upgrades tucked under a card
are folded into `stackSize` and are otherwise invisible — if you attach an upgrade to your
hero you will not see it listed separately.

## Hidden entries

Facedown cards and encounter/player card backs are collapsed into a single entry per zone:

```json
{ "name": "HIDDEN", "stackSize": 38 }
```

- `stackSize` is the **total** hidden count in that zone — useful (deck size, boost count).
- A `HIDDEN` entry has **only** `name` and `stackSize`. There is no `instanceId` and no
  `id` to pass to an action; doing so would address an arbitrary card in the merged group
  and is always wrong.

A zone can contain both real entries and one merged `HIDDEN` entry at once — for example
`playerNEngaged` holding a face-up side scheme plus a facedown boost card.

## Zones you care about

`N` is your player number.

| Group | Contents |
| --- | --- |
| `playerNHand` | Your hand. Each card is its own entry; you see all of them. |
| `playerNDeck` | Your deck. One `HIDDEN` entry; `stackSize` is the deck count. |
| `playerNDiscard` | Your discard. Listed card by card, face up. Fully readable. |
| `playerNPlay1` | Your identity row — your identity card lives here. |
| `playerNPlay2` | Your second play row: allies, supports, upgrades you put here. |
| `playerNEngaged` | Enemies engaged with you, side schemes dealt to you, and facedown boost cards. Note: cards here are controlled by `shared`, not by you. |
| `playerNEvent` | Staging area for an event card while it resolves. |
| `playerNNemesisSet` | Your nemesis set, out of play until triggered. Ignore it. |
| `sharedVillain` | The villain card. `tokens.damage` is damage dealt to the current stage. |
| `sharedMainScheme` | The main scheme. `tokens.threat` is current threat; `tokens.acceleration` is extra per-round threat. |
| `sharedEncounterDeck` / `sharedEncounterDiscard` | The encounter deck and discard. Read-only for you. |
| `sharedVillainDeck` / `sharedVillainDiscard` | Later and earlier villain stages. Read-only. |

`playerNPlay3` and `playerNPlay4` exist as groups but are not laid out in the standard
1–4 player layouts. Use `playerNPlay2` for your board; keep the identity alone in
`playerNPlay1`.

Card **side changes automatically on move**, set by the plugin's `onCardEnter`:

- Into any `*Deck` group → turns to side **B** (facedown).
- Into a hand, discard, or play group → turns to side **A** (faceup).

So `move_card` to `playerNDeck` puts the card facedown on top of your deck without you
needing a separate flip.

## Derived values you must compute yourself

| You want | Compute |
| --- | --- |
| Your remaining HP | `players.<you>.hitPoints` − (identity card `tokens.damage` or 0) |
| Whether you are about to be defeated | remaining HP ≤ incoming attack value |
| Villain remaining HP | `villainHitPoints` − (`sharedVillain[0].tokens.damage` or 0) |
| Cards actually in your hand | `len(zones["playerNHand"])` |
| Whether you must discard at end of phase | `len(zones["playerNHand"])` > `players.<you>.handSize` |
| Ally remaining HP | ally's catalog `health` − its `tokens.damage` |
| Minion remaining HP | minion's catalog `health` − its `tokens.damage` |
| Side scheme threat remaining | catalog `starting_threat` − removed, tracked via `tokens.threat` |

## What the state does NOT give you

None of the printed card values are in the state. To get them, call
`search_cards_marvel_champions(name="<card name>")` and match the result whose
`database_id` equals the state card's `id`. Useful attributes:

`cost`, `resource` (icon: `{m}` mental, `{p}` physical, `{e}` energy, `{w}` wild),
`attack`, `thwart`, `defense`, `health`, `hand`, `recover`, `rules`, `traits`,
`classification` (aspect), `type_code`, `unique`, `boost`, `scheme`, `stage`.

The search also accepts `type_code` (`hero`, `alter_ego`, `ally`, `event`, `upgrade`,
`support`, `resource`, `minion`, `villain`, `main_scheme`, `side_scheme`, `attachment`,
`treachery`, `obligation`), `classification`, `official_only`, and `limit`.

Your identity card appears **twice** in the catalog under the same `database_id`: once
with `type_code: "hero"` (attack / thwart / defense / hand size) and once with
`type_code: "alter_ego"` (recover / hand size / alter-ego ability). Look up both.

**Two things you genuinely cannot get:**

1. **Main scheme target threat.** It lives on the scheme's B face in the raw state, which
   is not exposed, and the catalog's B-face record is missing for some scenarios. If your
   scheme's B-face record exists (search the scheme name, look for a `stage` ending in
   `B`), its `target_threat` is the threshold. Otherwise ask the coordinator or human for
   it once and remember it. Do not guess.
2. **Which card is under a stack or behind a `HIDDEN` entry.** Treat it as unknown.

## Other read-only tools

- `list_actions()` — the generic action catalog. Small, occasionally useful.
- `get_session_actions(session_id)` — **large.** Returns every plugin action list and all
  group metadata. It will flood your context. Do not call it during play; this skill
  already contains what you would learn from it.
- `list_games()`, `lookup_session_by_slug(room_slug)` — session discovery. You do not need
  `lookup_session_by_slug` to act on a session: a room slug works directly as `session_id`
  on every tool. Call it only when you want the session's full metadata or its UUID.
