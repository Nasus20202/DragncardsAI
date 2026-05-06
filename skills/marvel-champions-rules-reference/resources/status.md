# Marvel Champions — Status Cards

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## GENERAL RULES

- A character cannot have more than **one status card of each type** at a time.
  - Exception: characters with the **Steady** keyword can have up to two of each type.
- Status card abilities have **timing priority over all conflicting triggered abilities**.
- When a character is given a status card: take one from the supply and place it on that character.

---

## CONFUSED

**Cancels a character's next scheme or thwart.**

### Giving Confused

- An ability "confuses" a character -> give that character a **confused status card**.
- "Cannot be confused" -> confused status cards cannot be placed on that character.

### Effect on Identity / Ally

- Attempts to **thwart** or use a **thwart ability**: discard the confused status card instead.
- All costs associated with the thwart attempt (including exhausting the character) **must still be paid**.
- A confused character CAN attempt to thwart even with **no valid target** (to spend the status card).

### Effect on Villain / Minion

- Would **scheme**: discard the confused status card instead.

### After Cancellation

- The thwart/scheme was replaced by removal of the confused card.
- Character is **NOT** considered to have thwarted or schemed.

---

## STUNNED

**Cancels a character's next attack.**

### Giving Stunned

- An ability "stuns" a character -> give that character a **stunned status card**.
- "Cannot be stunned" -> stunned status cards cannot be placed on that character.

### Effect on Identity / Ally

- Attempts to **attack** or use an **attack ability**: discard the stunned status card instead.
- All costs associated with the attack attempt (including exhausting the character) **must still be paid**.
- A stunned character CAN attempt to attack even with **no valid target** (to spend the status card).

### Effect on Villain / Minion

- Would **attack**: discard the stunned status card instead.

### After Cancellation

- The attack was replaced by removal of the stunned card.
- Character is **NOT** considered to have attacked.

---

## TOUGH

**Prevents a character from taking damage.**

### Effect

- If character with tough would take **any amount** of damage: prevent ALL of that damage; discard **one** tough status card.
- Multiple tough status cards on one character: discard only **one** per damage event.

### Hero + Basic Defense

- DEF reduces damage **first**. If reduced to 0: hero keeps tough status card (tough not triggered).
- If damage remains after DEF reduction: tough prevents it; tough card discarded.

### Overkill Interaction

- Ally/minion with tough is dealt excess damage from an overkill attack -> overkill damage is **NOT** dealt to identity/villain.

### After Tough Triggers

- Character is **NOT** considered to have taken damage.

---

## STEADY (KEYWORD INTERACTION)

- Character with Steady: not stunned unless it has **two** stunned status cards; not confused unless it has **two** confused status cards.
- After that character's attack/scheme/thwart is canceled by a status card effect: remove **all** status cards of that type from that character.

---

## VULNERABLE (KEYWORD INTERACTION)

- When a character with Vulnerable becomes confused or stunned: **immediately discarded**.
- If would simultaneously take enough damage to defeat it AND become confused/stunned: discarded **before** damage is applied; NOT considered defeated.
- Steady + Vulnerable: vulnerable does not trigger until character has **two** confused or stunned cards.

---

## STALWART (KEYWORD INTERACTION)

- Character with Stalwart **cannot be stunned or confused**.
- If character gains Stalwart while already having stunned/confused status cards: those cards are **immediately removed**.

---

## STATUS CARD TIMING NOTES

- Status cards resolve at **priority level 2** (above all triggered abilities, below constant abilities and delayed/lasting effects).
- A constant effect reducing damage to 0 takes priority over tough (constant = priority 1).
- An interrupt ability that would reduce damage to 0 does NOT take priority over tough (interrupt = priority 4).
