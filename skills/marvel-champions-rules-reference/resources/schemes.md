# Marvel Champions — Schemes & Threat

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## MAIN SCHEME

### Role

The villain's primary objective. Cannot be discarded from play.

### Threat Placement (Villain Phase Step 1)

- Place threat equal to main scheme's **acceleration field** (bottom-right corner).
- Add 1 additional threat per **acceleration icon** in play.
- Add 1 additional threat per **acceleration token** in play.

### Completing the Main Scheme

- When threat on main scheme >= **target threat value** (upper-left corner): scheme is **completed**; main scheme deck **advances**.
- If main scheme advances by OTHER means (not meeting threshold): **NOT** considered completed.
- If the **final stage** is completed: **villain wins the game**.

### Advancing the Main Scheme Deck

```
1. Remove top main scheme card from game.
   - Return all tokens EXCEPT acceleration tokens to token pool.
   - Discard each card attached to it.
2. Resolve any "When Revealed" ability on the "A" side of the new top card.
3. Flip new top card to its "B" side.
   - Place threat equal to its starting threat value.
   - Resolve any "When Revealed" ability on that side.
```

- **Excess threat:** does NOT carry over to new stage.
- **Acceleration tokens:** DO carry over to new stage.

---

## SIDE SCHEMES (ENCOUNTER)

- Revealed -> enters villain's play area.
- Enters with threat equal to **starting threat value** (bottom of card).
- Remains in play until:
  - Threat = 0 -> defeated and **discarded** (or **victory display** if Victory X).
  - Card ability removes it.
- Threat removed by: hero/ally thwarts, card abilities.

---

## PLAYER SIDE SCHEMES

- Enters villain's play area (next to main scheme).
- Enters with threat equal to **starting threat value**.
- **Player side scheme limit:**
  - 1-2 players: limit of **1**.
  - 3-4 players: limit of **2**.
  - If exceeded: first player immediately discards excess player side schemes.
- Defeated when threat = 0 -> discarded or victory display.
- Any ability referring to "schemes" or "side schemes" also applies to player side schemes.
- Heroes and allies CAN perform basic thwarts on player side schemes.

---

## SCHEME (CARD TYPE) — GENERIC RULES

The word "scheme" refers to all three types: main scheme, side schemes, and player side schemes.

- "Place threat on a scheme" / "remove threat from a scheme": the player resolving that ability **chooses** which scheme.
- Abilities removing threat from "a scheme" or "a side scheme" can affect player side schemes.

---

## THREAT

### Placing Threat

- Threat is placed on schemes via villain phase step 1, enemy scheme activations, card abilities, and keywords (Hinder X, Incite X).
- When threat is prevented: reduce the amount being placed before it is placed.

### Removing Threat

- Via basic thwart, thwart-labeled abilities, card abilities.
- **Crisis icon in play:** player cards **cannot** remove threat from the **main scheme**.
  - Encounter card abilities are NOT affected by the crisis icon.
  - Side schemes can still be thwarted while crisis icon is in play (only main scheme is blocked).

### Target Threat

- The threshold value shown in the upper-left corner of the main scheme card (before the title).
- When threat >= target threat: scheme completes.

---

## ACCELERATION ICONS & TOKENS

|                      | Acceleration Icon                                             | Acceleration Token                              |
| -------------------- | ------------------------------------------------------------- | ----------------------------------------------- |
| Source               | Printed on encounter cards                                    | Placed via card effects or empty encounter deck |
| Counts as the other? | No                                                            | No                                              |
| Effect               | +1 threat on main scheme per icon during villain phase step 1 | Same                                            |
| Removed by           | Defeating the encounter card it's on                          | See below                                       |

**Acceleration token placement:**

- When encounter deck is empty: place 1 acceleration token next to main scheme.
- Card effects may also add tokens.
- Tokens placed on cards OTHER than main scheme: still add threat; removed when that card leaves play.
- Tokens on the **main scheme**: **cannot be removed** from play; NOT discarded when main scheme card advances (carry over).

---

## ENEMY SCHEME ACTIVATION (SUMMARY)

When an enemy schemes:

1. Villain/villainous minion gets 1 facedown boost card (others skip).
2. Resolve boost cards (flip, resolve Boost abilities, add SCH icons, discard each).
3. Place threat on main scheme equal to enemy's **modified SCH** value.

See full detail in [combat-enemy.md](combat-enemy.md).
