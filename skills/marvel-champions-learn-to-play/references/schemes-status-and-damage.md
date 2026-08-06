# Schemes, Status Cards, and Dealing Damage

Covers the scheme deck and how threat advances it, the three side-scheme icons, how damage is
applied to each kind of target, and the three status cards.

**Referenced by:** SKILL.md

---

## The Scheme Deck

- Represents the villain's primary objective.
- If the villain completes the **final stage** of the scheme deck, players **lose immediately**.
- Some main schemes start with threat already on them (indicated at the bottom of the card).
- Each main scheme has a **target threat value** (top-left corner).
- Threat is checked **continuously** — the moment threat ≥ target, the scheme deck **advances** to the next stage. Threat from the previous stage is removed and returned to the token pool.

---

## Side Scheme Icons

| Icon | Name             | Effect                                                                   |
| ---- | ---------------- | ------------------------------------------------------------------------ |
| ⚡   | **Crisis**       | Must be defeated before threat can be removed from the main scheme       |
| ➕   | **Acceleration** | Each copy adds +1 threat placed during Step 1 of the villain phase       |
| ⚠️   | **Hazard**       | Each copy causes one additional encounter card to be dealt during Step 3 |

---

## Dealing Damage

| Target             | Mechanic                                                                                                                                                                                                     |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Minion or Ally** | Place damage tokens on the card. Each damage = -1 HP. At 0 HP, the card is defeated and placed in its owner's discard pile.                                                                                  |
| **Player**         | Decrease the player's hit points. At 0 HP, player is **eliminated**.                                                                                                                                     |
| **Villain**        | Decrease the villain's hit points. At 0 HP, the current villain stage is defeated; advance to next stage and set HP to the new stage's indicated value. If the final stage is defeated, players **win**. |

---

## Status Cards

### Confused (Purple)

- If a confused character would **thwart or use a thwart ability**: discard the Confused card instead. (Character still exhausts if the action would require it.)
- If a confused **villain** would scheme: discard the Confused card instead.

### Stunned (Yellow/Green)

- If a stunned character would **attack or use an attack ability**: discard the Stunned card instead. (Character still exhausts if the action would require it.)
- If a stunned **villain** would attack: discard the Stunned card instead.

### Tough (Orange)

- If a character with Tough would take **any amount of damage**: prevent all damage and discard the Tough card instead.

For steady / stalwart / vulnerable interactions and status replacement-effect timing, load
`marvel-champions-rules-reference/resources/status.md`.
