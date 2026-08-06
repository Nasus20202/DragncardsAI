# The Villain Phase in Detail

Covers the five villain-phase steps — threat placement, villain and minion activations with boost
cards, dealing and revealing encounter cards by card type, and surge, obligations, and nemesis
side schemes.

**Referenced by:** SKILL.md

---

## Step 1 — Place Threat

- Place threat equal to the **acceleration field value** on the main scheme.
- Each **side scheme with an acceleration icon** in play adds **+1 threat** placed this step.

---

## Step 2 — Villain and Minion Activations

The villain activates **once per player**, in player order. After the villain activates against a player, each **minion engaged with that player** also activates.

**Activation behavior depends on the player's form:**

### If Player is in ALTER-EGO Form → Enemies SCHEME

1. Give the villain a **facedown boost card** from the encounter deck.
2. Flip the boost card face up. For each **boost icon** (bottom-right), villain gets **+1 SCH** for this activation. (A star icon does not give +1 SCH — it triggers a special ability instead.)
3. Discard the boost card.
4. Place threat on the main scheme equal to villain's **modified SCH value**.
5. Each engaged minion **schemes** (no boost cards dealt to minions): place threat = minion's SCH.

### If Player is in HERO Form → Enemies ATTACK

1. Give the villain a **facedown boost card** from the encounter deck.
2. Attacked player decides whether to **defend**:
   - Defend: exhaust the hero themselves, or exhaust an ally they control.
   - If attacked player doesn't defend, **any other player** may defend by exhausting their hero or an ally.
3. Flip the boost card face up. For each **boost icon**, villain gets **+1 ATK**. (Star icon = special ability, not +1 ATK.)
4. Discard the boost card.
5. Deal damage equal to villain's **modified ATK value**:
   - **Hero defending:** Damage reduced by hero's DEF; remaining damage dealt to that hero.
   - **Ally defending:** All attack damage dealt to that ally.
   - **No defender:** All damage dealt to the player's hero.
6. Each engaged **minion attacks** (no boost cards, uses minion's ATK value). Resolve same as steps 2 and 4.

---

## Step 3 — Deal Encounter Cards

- Deal **one encounter card facedown** to each player in player order.
- If a side scheme with a **hazard icon** is in play, deal **one additional card** per hazard icon (in player order — first additional card to first player, etc.).

---

## Step 4 — Reveal Encounter Cards

Reveal and resolve encounter cards **one at a time, in player order**.

| Card Type       | Resolution                                                          |
| --------------- | ------------------------------------------------------------------- |
| **Minion**      | Enters play **engaged** with the player who revealed it             |
| **Treachery**   | Resolve effect, then place in encounter discard pile                |
| **Attachment**  | Enters play attached to the villain                                 |
| **Side Scheme** | Enters play near the main scheme with starting threat already on it |

**Side Scheme threat removal:** Heroes/allies can use basic thwart power or card abilities to remove threat. If a side scheme reaches 0 threat, discard it to the encounter discard pile.

### When Revealed Abilities

- Resolve immediately after the card enters play.
- For treacheries (which don't enter play): resolve the "When Revealed" ability, then discard.

### When Defeated Abilities

- Trigger when players defeat the minion, villain stage, or scheme that has the ability.

### Form-Specific Encounter Abilities

- If a revealed card has an ability specifying **"Hero"** or **"Alter-Ego"**, resolve it only if the **player revealing the card** is in that form.

### Nemesis Side Schemes

- When a card instructs a player to put a nemesis side scheme into play:
  - Place the **nemesis side scheme** in the play area.
  - Put the **nemesis minion** into play engaged with that player.
  - Place all other associated nemesis cards in the **encounter discard pile**.

### Obligations

- When an obligation is revealed, **immediately give it** to the player controlling the indicated character.
- That player follows the instructions to resolve it.

### Surge Keyword

- If a revealed encounter card has the **surge** keyword, that player immediately draws and reveals an **additional card** from the encounter deck.

---

## Step 5 — Pass First Player Token and End Round

- Pass the first player token **clockwise** to the next player.
- End the round; begin the next player phase.
