# The Player Phase in Detail

Covers what a player may do on their turn, how resource costs are paid, the other triggered
ability types, and what happens at the end of the player phase.

**Referenced by:** SKILL.md

---

## End of the Player Phase

- Players take turns **in player order**.
- After all players have taken a turn:
  1. Each player may discard cards and **must** discard down to hand size if over.
  2. Each player draws back up to their hand size.
  3. Each player readies **all** of their cards.
- Then proceed to the Villain Phase.

---

## Player Turn

On their turn, a player may perform the following actions **in any order**, as many times as desired (unless noted):

### 1. Change Form _(once per turn only)_

- Flip identity card to **hero side** or **alter-ego side**.
- Character remains in the same ready/exhausted state.
- All upgrades, attachments, tokens, damage, and status cards remain.

### 2. Play a Card

**Steps:**

1. Place the card on the table.
2. Pay the card's **resource cost** (see Resource Costs).
3. Resolve entry:
   - **Ally / Upgrade / Support:** Enters play ready in the player's play area.
   - **Event:** Resolve effects, then place in owner's discard pile.

**Ally Limit:** Each player may control **up to 3 allies** at a time. If playing a 4th, immediately discard one previously controlled ally.

### 3. Use a Basic Power

**Requires:** Character must be in the form that has the power.

**Steps:**

1. Declare the power.
2. Pay the cost by **exhausting** the hero or alter-ego.
3. Resolve the effect.

| Power              | Form      | Effect                                                                                 |
| ------------------ | --------- | -------------------------------------------------------------------------------------- |
| **Basic Attack**   | Hero      | Deal damage = ATK value to one eligible enemy (villain or minion)                      |
| **Basic Thwart**   | Hero      | Remove threat = THW value from one scheme of choice                                    |
| **Basic Defense**  | Hero      | Exhaust to prevent damage = DEF value from an attack (can defend self or another hero) |
| **Basic Recovery** | Alter-Ego | Heal HP = REC value (cannot exceed max HP)                                             |

**Basic Defense notes:**

- Can only be used **when a hero is being attacked**.
- A hero may defend **themselves or any other hero**.
- Damage exceeding DEF is dealt to the defending hero.

### 4. Use an Ally

**Steps:**

1. Exhaust the ally.
2. Declare: **attack** an enemy or **thwart** a scheme.
3. Declare target enemy or scheme.
4. Resolve: deal damage (attack) or remove threat (thwart) equal to ally's relevant stat.
5. Deal **consequential damage** to the ally:
   - If ally attacked: deal damage shown under ATK to the ally.
   - If ally thwarted: deal damage shown under THW to the ally.

### 5. Trigger an Action Ability

- Action abilities are marked with bold **"Action"**.
- Can be triggered from cards in play, encounter cards in play, or event cards played from hand.
- If preceded by **"Hero Action"** or **"Alter-Ego Action"**, player must be in that form.

**Steps:**

1. Declare which action ability to trigger.
2. Pay the cost (resources, exhausting, etc.). Cost is separated from effect by **→**.
3. Resolve the effect.

A given action ability may be triggered **any number of times** per turn, so long as cost can be paid and effect can change the game state.

### 6. Ask Another Player to Trigger an Action

- A player may ask another player to trigger an Action on a card they control or an event card in their hand.
- The other player **decides** whether to do so.
- Other players may also **volunteer** to use an action during the active player's turn.

---

## Resource Costs

Resources are generated in two ways:

| Method               | How                                                                                    |
| -------------------- | -------------------------------------------------------------------------------------- |
| **Discard a card**   | Generates resources equal to the resource icons shown in the card's bottom-left corner |
| **Resource ability** | Use a card with a "Resource" ability to generate the specified resource                |

**Resource Types:**

| Icon | Type         | Notes                                      |
| ---- | ------------ | ------------------------------------------ |
| 🔵   | **Mental**   |                                            |
| 🟤   | **Physical** |                                            |
| ⚡   | **Energy**   |                                            |
| ⭐   | **Wild**     | May be used as Mental, Physical, or Energy |

- Any excess resources beyond the cost are **lost**.
- Generally, **any combination** of resource types may pay a card's cost.
- Some abilities require a **specific type** (or combination).

---

## Other Triggered Abilities

In addition to Actions, three other triggered ability types exist:

| Type          | When Used                                                         | Notes                                               |
| ------------- | ----------------------------------------------------------------- | --------------------------------------------------- |
| **Interrupt** | Immediately **before** the specified condition occurs             | Can prevent or change an occurrence                 |
| **Response**  | Immediately **after** the specified condition occurs              |                                                     |
| **Resource**  | When the controlling player is generating resources to pay a cost | Unless noted, only the card's controller can use it |

- These are **optional** unless preceded by **"Forced"**.
- Each copy may be used **once per triggering occurrence**.

For precedence between simultaneous triggers, load
`marvel-champions-rules-reference/resources/timing.md`.
