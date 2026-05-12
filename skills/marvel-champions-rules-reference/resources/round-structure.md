# Marvel Champions — Round Structure

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## FULL ROUND OVERVIEW

Each game round proceeds in this order:

| Step | Phase                              | Detail                                   |
| ---- | ---------------------------------- | ---------------------------------------- |
| 1    | Player Phase begins                | —                                        |
| 2    | Each player takes a turn           | In player order                          |
| 3    | Player Phase ends                  | Hand size check, draw, ready             |
| 4    | Villain Phase begins               | —                                        |
| 5    | Place threat on main scheme        | Acceleration field + tokens/icons        |
| 6    | Villain and minions activate       | In player order                          |
| 7    | Deal encounter cards               | 1 per player + 1 per hazard icon         |
| 8    | Reveal and resolve encounter cards | First player first, then in player order |
| 9    | Pass the first player token        | Clockwise                                |
| 10   | End the round                      | Proceed to step 1 of next round          |

---

## PLAYER PHASE

During the player phase, each player (in **player order**) takes one turn.

### PLAYER TURN

During their turn, a player may perform the following options in **any order**. All options except "change form" may be performed **as many times as the player is able**, so long as they can pay the required costs.

| Option                                                                                           | Limit             | Requirement                                 |
| ------------------------------------------------------------------------------------------------ | ----------------- | ------------------------------------------- |
| **Change form** (hero ↔ alter-ego)                                                              | **Once per turn** | —                                           |
| **Play** an ally, upgrade, support, or player side scheme from hand                              | Unlimited         | Pay resource cost                           |
| **Use basic recovery**                                                                           | Unlimited         | Must be in alter-ego form                   |
| **Use basic attack or thwart**                                                                   | Unlimited         | Must be in hero form; valid target required |
| **Use an ally** to attack an enemy or thwart a scheme                                            | Unlimited         | Ally must exhaust                           |
| **Trigger an "Action" ability** on a card they control, an encounter card, or an event from hand | Unlimited         | Pay costs; meet play restrictions           |
| **Ask another player** to trigger any "Action" they could trigger on their own turn              | Unlimited         | Other player decides whether to act         |

- If an action ability is preceded by "Hero" or "Alter-Ego," the player must be in the **specified form**.
- Another player may also **offer** to use an action during the active player's turn unprompted.

### END OF PLAYER PHASE

Performed once, after all players have taken their turns:

1. In player order, each player may discard any number of cards from their hand; must discard down to hand size if over.
2. Each player **simultaneously** draws up to their hand size.
3. Each player **simultaneously** readies all of their cards. Ready each exhausted encounter card.
4. Any effects lasting "until the end of the [player] phase" **end**.
5. Resolve any "when/after the [player] phase ends" effects.

> **Note:** "Until end of player phase" effects expire _after_ steps 2–3 (draw and ready), not before.

---

## VILLAIN PHASE

### Step 1 — Place Threat

Place threat equal to the main scheme's **acceleration field** (bottom-right corner) onto that scheme. All active acceleration tokens and acceleration icons each add 1 additional threat.

### Step 2 — Enemies Activate (in player order)

For each player, in player order:

- **a.** The villain activates against that player.
  - Player in **hero form** → villain initiates an attack.
  - Player in **alter-ego form** → villain initiates a scheme.
- **b.** Each minion engaged with that player activates against them, one at a time in that player's choice of order.
  - Engaged player in **hero form** → minion initiates an attack.
  - Engaged player in **alter-ego form** → minion initiates a scheme.

**Each villain activation:** Give the villain one facedown boost card from the encounter deck.

**Minions with villainous keyword:** Also given a boost card when they activate.

**If an activating minion leaves play:** That minion's activation ends immediately; no further steps of that activation resolve.

**Nested activations:** If an effect initiates an activation during the resolution of another activation, the new activation resolves after the current one finishes. If multiple activations are initiated this way, the first player decides the order. All abilities triggered by the initial activation resolve before subsequent activations initiate.

### Step 3 — Deal Encounter Cards

- Deal **one encounter card** to each player (facedown).
- Deal **one additional card** for each hazard icon (⚠) on cards in play. Additional cards are dealt in player order (first additional to first player, second additional to second player, etc.).
- In heroic mode: deal X additional encounter cards to **each player**, where X = the chosen heroic level number.

### Step 4 — Reveal Encounter Cards

The first player reveals each of their encounter cards, **one card at a time in the order they were dealt**, resolving each card based on its card type. Each player repeats this process in player order until no dealt encounter cards remain.

**To reveal an encounter card:**

1. Turn the encounter card faceup.
2. Based on card type:
   - **Attachment** → enters play attached to the specified game element.
   - **Environment** → enters play in the villain's play area.
   - **Minion** → enters play in the revealing player's play area; engages that player.
   - **Obligation** → enters play in the revealing player's play area (or specified player's play area).
   - **Side scheme** → enters play in the villain's play area.
   - **Treachery** → placed on the table in front of the revealing player (not in play).
   - **Other** → placed on the table in front of the revealing player (not in play).
3. Resolve each "**When Revealed**" ability on that card (including those from keywords).
4. If the card is a **treachery**, discard it.

### Step 5 — Pass First Player Token

Pass the first player token to the **next clockwise player**.

### Step 6 — End of Villain Phase and Round

- **a.** Any effects lasting "until the end of the [villain] phase" or "until the end of the round" **end**.
- **b.** Resolve any "when/after the [villain] phase ends" or "when/after the round ends" effects.

---

## FIRST PLAYER

- Determined by the players at the beginning of the game.
- Indicated by the **first player token**.
- If the first player is **eliminated**, the token immediately passes clockwise.

**The first player decides:**

- If an encounter card targets a specific player/card with multiple eligible targets.
- If an encounter card requires a card ability, game function, or choice without specifying which player acts.
- If two or more effects would resolve simultaneously.

**The first player has timing priority:**

- First opportunity to use an **interrupt** at each appropriate game moment; then proceeds clockwise.
- First opportunity to use a **response** at each appropriate game moment; then proceeds clockwise.

---

## IN PLAYER ORDER

If players are instructed to perform a sequence "in player order":

- The **first player** performs their part first.
- Followed by the other players in **clockwise order**.
- If the sequence doesn't conclude after each player has gone once, it continues **clockwise** until complete.
- "**Next player**" always refers to the next clockwise player.

---

## ENCOUNTER DECK — EMPTY DECK RULES

| Situation                                                                   | Result                                                                                                                    |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Encounter deck empties                                                      | Immediately shuffle encounter discard pile into a new encounter deck; place 1 acceleration token next to main scheme deck |
| Both encounter deck AND encounter discard pile are empty simultaneously     | Infinite acceleration tokens → **players lose**                                                                           |
| Card ability discards cards from encounter deck and deck empties mid-effect | Ability is considered fulfilled; do NOT continue discarding from the newly shuffled deck                                  |
| Player deck empties                                                         | Shuffle player discard pile into a new deck; player immediately deals themselves 1 facedown encounter card                |
| Player deck empties and discard pile is also empty                          | Deck does not reset until at least 1 card enters the discard pile; then deal 1 facedown encounter card                    |
