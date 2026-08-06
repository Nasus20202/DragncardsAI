# Quick Reference

At-a-glance tables and flow diagrams — stat abbreviations, the villain-phase and player-turn
summaries, resource icons, side-scheme icons, status-card effects, and boost-card icons.

**Referenced by:** SKILL.md

---

## Abbreviations

| Abbreviation | Meaning    |
| ------------ | ---------- |
| ATK          | Attack     |
| DEF          | Defense    |
| REC          | Recover    |
| SCH          | Scheme     |
| THW          | Thwart     |
| HP           | Hit Points |

## Villain Phase Summary

```
1. Place Threat on Main Scheme
      └─ +1 per Acceleration side scheme in play
2. Villain Activates (once per player, in player order)
      ├─ Player in ALTER-EGO → Villain SCHEMES
      │      └─ Draw boost card, flip, apply +SCH per boost icon
      │         Place threat = modified SCH on main scheme
      │         Engaged minions also scheme (no boost cards)
      └─ Player in HERO → Villain ATTACKS
             └─ Draw boost card
                Attacked player may defend (exhaust hero or ally)
                Flip boost card, apply +ATK per boost icon
                Deal modified ATK damage (reduced by DEF if hero defending)
                Engaged minions also attack (no boost cards)
3. Deal 1 encounter card to each player
      └─ +1 per Hazard side scheme in play (in player order)
4. Reveal encounter cards (in player order)
      ├─ Minion → enters play engaged with that player
      ├─ Treachery → resolve effect, discard
      ├─ Attachment → attaches to villain
      └─ Side Scheme → enters play with starting threat
5. Pass first player token clockwise
```

## Player Turn Summary

```
On your turn (any order, any number of times):
  ├─ Change Form (hero ↔ alter-ego) [ONCE PER TURN]
  ├─ Play a card (pay cost, enter play or discard)
  ├─ Use Basic Power (exhaust hero/alter-ego)
  │    ├─ Hero: Basic Attack (ATK damage to one enemy)
  │    ├─ Hero: Basic Thwart (remove THW threat from one scheme)
  │    ├─ Hero: Basic Defense (exhaust to reduce ATK by DEF when attacked)
  │    └─ Alter-Ego: Basic Recovery (heal REC hit points)
  ├─ Use an Ally (exhaust → attack enemy or thwart scheme → take consequential damage)
  └─ Trigger an Action ability (pay cost → resolve effect)
```

## Resource Icons

| Icon | Type            |
| ---- | --------------- |
| 🔵   | Mental          |
| 🟤   | Physical        |
| ⚡   | Energy          |
| ⭐   | Wild (any type) |

## Side Scheme Icons

| Icon | Name         | Effect                                                       |
| ---- | ------------ | ------------------------------------------------------------ |
| ⚠️   | Hazard       | +1 encounter card dealt per copy in Step 3                   |
| ➕   | Acceleration | +1 threat placed per copy in Step 1                          |
| 🚫   | Crisis       | Main scheme cannot have threat removed while this is in play |

## Status Card Effects

| Status       | Affected Character | Effect                                                                          |
| ------------ | ------------------ | ------------------------------------------------------------------------------- |
| **Confused** | Hero/Ally          | Next thwart attempt: discard Confused instead (still exhaust if required)       |
| **Confused** | Villain            | Next scheme: discard Confused instead                                           |
| **Stunned**  | Hero/Ally          | Next attack attempt: discard Stunned instead (still exhaust if required)        |
| **Stunned**  | Villain            | Next attack: discard Stunned instead                                            |
| **Tough**    | Any                | Next time damage would be taken (any amount): prevent all damage, discard Tough |

## Boost Card Icons

| Icon                | Meaning                                                                  |
| ------------------- | ------------------------------------------------------------------------ |
| Standard boost icon | +1 to ATK (attack) or SCH (scheme) for this activation                   |
| ⭐ Star icon        | Does NOT provide +1; triggers a special ability from the card's text box |

---

_© MARVEL. Rules based on the Marvel Champions: The Card Game core set Learn to Play booklet._
