# Marvel Champions — Enemy Attacks & Activations

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## ACTIVATION TYPES

Every enemy activation is either an **attack** or a **scheme**.

| Engaged player's form | Villain does                   | Minion does                    |
| --------------------- | ------------------------------ | ------------------------------ |
| Hero form             | Attacks that player's identity | Attacks that player's identity |
| Alter-ego form        | Schemes                        | Schemes                        |

- Villain activates **once per player** (player order) in villain phase step 2.
- Each engaged minion activates against the player it is engaged with.
- Card abilities can also cause enemy activations outside of step 2.

### Multiple Simultaneous Activations Against You

- Resolve villain first (if any), then minions in **your choice** of order.

### Nested Activations

- If an activation is initiated mid-activation: new one resolves **after** current finishes.
- Multiple nested activations: first player decides order.
- All abilities triggered by the initial activation resolve before subsequent activations initiate.

### Minion Leaves Play Mid-Activation

- Activation ends immediately; no further steps resolve.

### Newly Engaged Minion During Activation

- If all engaged minions are instructed to activate (e.g., via Boost ability during step 2) and a new minion engages: that minion **also activates**.

---

## ATTACK RESOLUTION (STEP BY STEP)

### Step 1 — Boost Card

- **Villain**: always gets 1 facedown boost card from encounter deck.
- **Minion with Villainous**: gets 1 facedown boost card.
- **Minion without Villainous**: skip this step.
- If enemy is given a boost card outside its own activation: card stays facedown until enemy activates (villain/villainous minion still gets another boost at start of its next activation).

### Step 2 — Declare Defender (optional)

- Only **one player** may defend; others cannot intervene simultaneously.
- **Hero (basic defense):** exhaust hero; damage reduced by DEF; remainder dealt to hero.
  - If DEF reduces damage to 0: hero keeps tough status card (if any).
  - Declaring hero the defender via card ability = basic defense.
- **Ally:** exhaust ally; ALL damage dealt to ally; no carry-over to identity if defeated.
  - If defending ally leaves play **before damage is dealt**: attack becomes undefended; identity of ally's controller becomes new target.
- **Defense-labeled ability** (e.g., "Hero Interrupt (defense)"):
  - Identity becomes defender (if no defender already).
  - NOT a basic defense; does NOT reduce damage by DEF; hero does not exhaust (unless stated).
  - Multiple defense abilities may be resolved by defending player during one attack.
  - Once one player uses a defense ability: other players cannot use defense abilities for that attack.
  - Exception: if an ally is already defending, player can still use defense ability WITHOUT identity becoming defender.
  - Can be triggered outside of an attack if triggering condition is met (identity not considered to have defended an attack).
- **If another player defends:** that player becomes new target of the attack.

### Step 3 — Resolve Boost Cards (one at a time, in dealt order)

```
a. Flip boost card faceup
b. Resolve "Boost" ability (star icon in boost field) — ALL OTHER abilities on card are ignored
c. Add boost icons to enemy's ATK (if attacking) or SCH (if scheming) for this activation
d. Discard the boost card
e. Repeat for remaining boost cards
```

- Star icon != boost icon; does not add to ATK/SCH.
- Boost abilities: cumulative across all boost cards for the activation.
- Damage from a boost ability is NOT damage from the activation itself.

### Step 4 — Deal Damage

- Damage = enemy's **modified ATK** value.
- **Hero basic defense:** reduce damage by DEF -> remainder to hero. Hero is considered attacked.
- **Ally defense:** all damage to ally. If defeated, additional damage does NOT carry over to identity. Ally is considered attacked.
- **Undefended (no defender, or defender left play):** all damage to targeted character. Targeted character is considered attacked.

### Step 5 — Post-Attack Abilities (in order)

```
a. Retaliate X keyword (if attacked character is still in play)
b. Forced abilities (any order):
   - "after [char] attacks [and damages/defeats] [you/an ally]"
   - "after [char] is attacked"
   - "after [char] defends [and takes no damage]"
   - "after [char] [takes/deals] damage"
c. Non-forced abilities with same triggers
```

### Additional Attack Rules

- Interrupts triggering "when [enemy name] attacks" = same timing as "when [the villain/an enemy] initiates an attack."
- If attack ends before damage is dealt: "after character defends" abilities resolve; "after enemy attacks" abilities do NOT.

---

## SCHEME ACTIVATION (STEP BY STEP)

### Step 1 — Boost Card

- Same rules as attack: villain/villainous minion gets 1 facedown boost card; others skip.

### Step 2 — Resolve Boost Cards

- Same process as attack (a-e above), but icons add to SCH value.

### Step 3 — Place Threat

- Place threat on main scheme equal to enemy's **modified SCH** value.

---

## "YOU" IN ATTACK CONTEXT

- **"When [enemy] attacks you"** -> player against whom attack **initiated**.
- **"After [enemy] attacks you"** -> player whose character **defended**.
- **Constant/boost "you"** abilities -> defending player.
- **Attacks against ally directly** -> player who controls the ally = attacked player.

---

## ATTACKS AGAINST ALLIES (DIRECTLY)

Some effects cause an enemy to attack an ally directly:

- Undefended damage placed on attacked ally.
- Player controlling ally = attacked player ("attacks you" abilities resolve against them).
- Boost abilities' "you" = player controlling attacked ally.
- Players may defend normally.
- **Overkill + ally defeated:** excess damage to identity of ally's controller (whether attacked ally or defending ally).
