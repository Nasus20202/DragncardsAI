# Marvel Champions — Timing & Priority Rules

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## SIMULTANEOUS TIMING PRIORITY

When two or more abilities share the **same triggering condition**, resolve them in this priority order:

| Priority    | Ability Type                                                                                             |
| ----------- | -------------------------------------------------------------------------------------------------------- |
| 1 (highest) | Constant abilities, delayed effects, lasting effects, keywords, acceleration/amplify/crisis/hazard icons |
| 2           | Status cards (Tough, Stunned, Confused)                                                                  |
| 3           | Forced Interrupt                                                                                         |
| 4           | Interrupt                                                                                                |
| 5           | Boost abilities, When Defeated abilities, When Revealed abilities                                        |
| 6           | Forced Response                                                                                          |
| 7           | Response                                                                                                 |
| 8 (lowest)  | Consequential damage                                                                                     |

**Rule:** If two or more effects have the same timing trigger and the same priority level, the **first player** determines the order in which they resolve.

---

## ABILITY TYPE REFERENCE

| Type             | Mandatory?              | Window                                                | Notes                                                                  |
| ---------------- | ----------------------- | ----------------------------------------------------- | ---------------------------------------------------------------------- |
| Constant         | Yes — always active     | Continuous                                            | Active as soon as card enters play                                     |
| Delayed Effect   | Yes — automatic         | Immediately at specified timing point                 | Has same priority as constant effects                                  |
| Lasting Effect   | Yes — continuous        | For its specified duration                            | Treated as constant ability during its duration                        |
| Keyword          | Yes                     | As specified by keyword                               | See keywords.md for individual keyword timing                          |
| Setup            | Yes                     | During game setup only                                | Player card abilities cannot resolve during setup without this trigger |
| When Revealed    | Yes                     | On reveal                                             | "When Revealed" on villain/main scheme cards cannot be canceled        |
| When Defeated    | Yes                     | On defeat                                             | Defeated card leaves play after "When Defeated" resolves               |
| When Completed   | Yes                     | When main scheme is completed                         |                                                                        |
| Forced Interrupt | Yes                     | Before triggering condition                           | Initiates before non-forced interrupts for the same condition          |
| Forced Response  | Yes                     | After triggering condition                            | Initiates before non-forced responses for the same condition           |
| Forced Action    | Yes (before phase ends) | Any valid action timing during player phase           | Must resolve before player phase can end                               |
| Boost            | Yes                     | When boost card is flipped faceup                     | Only text beneath the divider line is active on a boost card           |
| Interrupt        | No                      | Before triggering condition                           | Player choice; first player has first opportunity, then clockwise      |
| Response         | No                      | After triggering condition                            | Player choice; first player has first opportunity, then clockwise      |
| Action           | No                      | During player turn (or by request during other turns) |                                                                        |
| Resource         | No                      | While generating resources to pay a cost              |                                                                        |
| Special          | No                      | Only via explicit instruction of another card ability |                                                                        |

---

## INTERRUPT TIMING RULES

- An interrupt resolves **immediately before** its triggering condition resolves.
- Interrupts using the word **"would"** resolve before the triggering condition **initiates** (when the condition becomes imminent).
- Each interrupt can only be triggered **once per occurrence** of its triggering condition.
- Multiple copies of the same card with an interrupt can each trigger on the same condition.
- If an interrupt **changes or cancels** an imminent triggering condition (via replacement effect): **no further interrupts** to the original triggering condition can be triggered.
- Once all players decline to use further interrupts on a triggering condition: that interrupt window is **closed** for that instance.
- The **first player** has the first opportunity to use an interrupt; then proceeds clockwise.
- Forced interrupts initiate **before** non-forced interrupts for the same triggering condition.

### "Would" vs. Standard Interrupt Timing

```
Standard:     [Trigger initiates] → [Interrupt window] → [Trigger resolves]
"Would":      [Trigger becomes imminent] → ["Would" interrupt window] → [Trigger initiates] → [Standard interrupt window] → [Trigger resolves]
```

---

## RESPONSE TIMING RULES

- A response resolves **immediately after** its triggering condition resolves.
- Each response can only be triggered **once per occurrence** of its triggering condition.
- Multiple copies of the same card with a response can each trigger on the same condition.
- If a single effect causes **multiple triggering conditions** to occur simultaneously, those conditions are handled with a **single interrupt window** and a **single response window**. During each window, abilities referring to any of those triggering conditions may be used in **any order**.
- Once all players decline to use further responses: that response window is **closed** for that instance.
- The **first player** has the first opportunity to use a response; then proceeds clockwise.
- Forced responses initiate **before** non-forced responses for the same triggering condition.

---

## DAMAGE RESOLUTION ORDER

When damage is dealt to a character, effects surrounding the dealing and taking of damage resolve in this order:

| Step | Timing Point                                                                                                                                |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | Abilities triggering **"when [character] would deal/be dealt any amount of damage..."**                                                     |
| 2    | **Tough status cards**                                                                                                                      |
| 3    | Abilities triggering **"when [character] would take any amount of damage..."**                                                              |
| 4    | Abilities triggering **"when [character] takes any amount of damage..."**                                                                   |
| 5    | **Placing of damage** on the character                                                                                                      |
| 6    | Abilities triggering **"when [character] would be defeated..."**                                                                            |
| 7    | Abilities triggering **"when [character] is defeated..."**                                                                                  |
| 8    | **"When Defeated" abilities**                                                                                                               |
| 9    | **Discarding** of a defeated character                                                                                                      |
| 10   | Abilities triggering **"after [character] deals/is dealt/takes any amount of damage..."** or **"after [character] defeats/is defeated..."** |

**Key distinction:**

- When the amount of damage an effect **deals** is modified → the amount **taken** is similarly modified.
- When the amount of damage a character **takes** is modified (e.g., prevented) → the amount **dealt** is NOT modified.

---

## ENEMY ATTACK RESOLUTION ORDER

When an enemy attack resolves, abilities trigger in this order after the attack finishes:

| Step | Ability                                                                                                                                                                                                                                                            |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| a    | **Retaliate X keyword** (if the attacked character is still in play)                                                                                                                                                                                               |
| b    | **Forced abilities** with these triggers (in any order): "after [character] attacks [and damages/defeats] [you/an ally]...", "after [character] is attacked...", "after [character] defends [and takes no damage]...", "after [character] [takes/deals] damage..." |
| c    | **Non-forced abilities** with the triggers listed above                                                                                                                                                                                                            |

**Note:** If an enemy attack ends before damage is dealt, defender-trigger abilities resolve, but attacker-trigger abilities do not.

---

## PLAYER ATTACK RESOLUTION ORDER

When a player attack resolves, abilities trigger in this order:

| Step | Ability                                                                                                                               |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 1    | **Retaliate X keyword** (if the attacked character was not defeated)                                                                  |
| 2    | **Forced abilities**: "after [character] attacks [and damages/defeats] [an enemy/a minion]..." and "after [character] is attacked..." |
| 3    | **Non-forced abilities** with the triggers listed above                                                                               |
| 4    | **Consequential damage** (for allies)                                                                                                 |

---

## RETALIATE X RESOLUTION ORDER

After a character with retaliate X is attacked:

| Step | Ability                                                                                                         |
| ---- | --------------------------------------------------------------------------------------------------------------- |
| 1    | Abilities triggering "after [character] takes any amount of damage..."                                          |
| 2    | **Retaliate X**                                                                                                 |
| 3    | Abilities triggering "after [character] is attacked..." or "after [character] attacks [and damages/defeats]..." |

**Requirement:** The character with retaliate X must **still be in play** after the attack resolves to deal this damage.

---

## FORCED ABILITY RULES

- If two or more forced abilities would initiate at the same moment: the **first player** determines the order, regardless of who controls those cards.
- Each forced ability must **resolve as completely as possible** before the next forced ability triggered by the same condition initiates.
- If a forced ability requires one or more targets to resolve and has **no valid targets**: it does **not** initiate. Any costs that would have been paid are not paid.
- **Forced Action** abilities can be triggered at any time during the player phase when a non-forced action could be triggered, but must be resolved **before the player phase can end**. If its cost cannot be paid or it has no valid targets, the phase can end without it resolving.

---

## LASTING EFFECTS — TIMING

- A lasting effect expires as soon as the timing point specified by its duration is reached.
- An "until the end of the round" lasting effect expires **just before** an "at the end of the round" ability or delayed effect may initiate.
- A lasting effect that expires at the end of a specified time period can only be **initiated during** that time period.

---

## SIMULTANEOUS RESOLUTION

If two or more effects with the **same bold timing trigger** would resolve simultaneously: the **first player determines the order** in which they resolve.

---

## DELAYED EFFECTS

- Delayed effects resolve **automatically and immediately** after their specified timing point or future condition occurs.
- They resolve **before** responses to that point or condition may be used.
- Delayed effects have the **same timing priority** as constant effects.
- When a delayed effect resolves, it is **not** treated as a new triggered ability.

---

## END OF PLAYER PHASE — SEQUENCE

1. In player order, each player may discard any number of cards; must discard down to hand size if over.
2. Each player **simultaneously** draws up to hand size.
3. Each player **simultaneously** readies all their cards. Ready each exhausted encounter card.
4. Any effects lasting "until the end of the [player] phase" **end**.
5. Resolve any "when/after the [player] phase ends" effects.

**Scope note:** Effects lasting "until the end of the [player] phase" end **after** players draw up to hand size and all cards are readied (steps 2–3), not before.

---

## END OF VILLAIN PHASE / ROUND — SEQUENCE

1. Any effects lasting "until the end of the [villain] phase" or "until the end of the round" **end**.
2. Resolve any "when/after the [villain] phase ends" or "when/after the round ends" effects.
