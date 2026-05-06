# Marvel Champions — Player Attacks, Thwarts & Defense

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## ATTACKS

### Basic Attack

- Character exhausts -> deals ATK damage to one enemy.
- **Requires:** valid attackable enemy OR character is stunned (to spend stun).
- Hero and ally attacks can target **any enemy** unless a card ability (e.g., Guard) prevents it.

### Attack-Labeled Ability ("Hero Action (attack)")

- Resolving that ability = attacking the specified target.
- Hero does **not** exhaust unless specified.
- Considered a **single attack** even if multiple damage instances.
- When attack ability damage is increased by another ability: each instance NOT using "additional" is increased by the specified amount.

### "Make the following X attacks in order"

- Each instance = a **separate attack**.
- An ability that increases damage of "an attack" increases only **one** of those attacks (but can be triggered separately for each).

### Multi-Target Attacks

- Character is considered to have attacked **each** target.
- Each attacked enemy with Retaliate X still in play deals its retaliate damage to the attacking character.

### Order of Resolution for Player Attack Abilities

```
1. Retaliate X keyword (if attacked character was not defeated)
2. Forced abilities (any order):
   - "after [char] attacks [and damages/defeats] [an enemy/a minion]"
   - "after [char] is attacked"
3. Non-forced abilities with same triggers
4. Consequential damage (for allies)
```

---

## THWARTS

### Basic Thwart

- Character exhausts -> removes THW threat from one scheme.
- **Requires:** scheme with >=1 threat OR character is confused (to spend confused).

### Thwart-Labeled Ability ("Hero Action (thwart)")

- Resolving = thwarting the specified scheme.
- Hero does **not** exhaust unless specified.
- Considered a **single thwart** even if multiple threat instances removed.
- If ability increases threat removed: each instance NOT using "additional" is increased.

### Assault Keyword (on a scheme)

- Basic thwart against an assault scheme: use **ATK instead of THW**.
- Ally uses ATK consequential damage icon after thwarting.
- Abilities increasing "basic power" can increase ATK used this way.

---

## DEFENSE (PLAYER-INITIATED)

### Basic Defense

- Hero exhausts during an enemy attack -> reduces damage by DEF; remainder dealt to hero.
- Hero IS considered to have been attacked.
- If DEF reduces damage to 0: hero keeps any tough status card.
- "Declare [hero] the defender" via card ability = basic defense.
- While a hero is making basic defense: no other friendly character can defend that attack.

### Ally Defense

- Any player may exhaust an ally they control to defend an attack against any attacked player.
- ALL damage from attack dealt to the ally.
- If ally is defeated: additional damage does **not** carry over to identity.
- If defending ally leaves play **before damage is dealt**: attack becomes undefended; identity of ally's controller becomes new target.
- "Declare [ally] the defender" via card ability = ally becomes defender.
- While ally is defending: no other friendly character can defend that attack.

### Defense-Labeled Ability ("Hero Interrupt (defense)")

- Initiating during an enemy attack -> identity becomes defender (if no defender already).
- Identity is considered defender **as soon as the ability begins resolving**.
- NOT a basic defense; does NOT reduce damage by DEF; hero does not exhaust (unless specified).
- "When your hero defends against an attack" abilities CAN trigger when resolving a defense-labeled ability.
- The defending player may resolve **any number** of defense abilities during one attack (as long as triggering conditions are met).
- Once one player resolves a defense-labeled ability: **other players cannot** resolve defense-labeled abilities for that attack.
- Exception: if the player's **ally** is defending, that player can still use a defense-labeled ability — identity does NOT become the defender.
- Can be triggered **outside of an attack** if triggering condition is met (identity not considered to have defended).

### Cross-Player Defense

- If a player (other than the attacked player) defends: defending player becomes **new target** of the attack.
- "When attacks you" -> player against whom attack initiated.
- "After attacks you" -> player whose character defended.
- Constant/boost "you" -> defending player.

### Undefended Attack

- No character defends, OR defending ally leaves play before damage is dealt.
- All damage dealt to the **targeted character**.

---

## CONSEQUENTIAL DAMAGE

- After ally **attacks**: takes damage = consequential damage icons under its ATK field.
- After ally **thwarts**: takes damage = consequential damage icons under its THW field.
- Dealt **after** resolving all triggered abilities from the attack/thwart.
- **No consequential damage if:**
  - Target leaves play before ally deals damage/removes threat (ally not considered to have attacked/thwarted; still exhausts).
  - Ally was stunned and the stun was spent (attack canceled).
  - Ally was confused and the confused was spent (thwart canceled).

---

## LABELED ABILITIES

A labeled ability has a parenthetical after its bold trigger: "(attack)", "(defense)", "(thwart)", or a combination.

- "(attack)" -> considered an attack by that player's identity.
- "(defense)" -> considered a defense by that player's identity; identity becomes defender during an attack.
- "(thwart)" -> considered a thwart by that player's identity.
- Multiple labels -> considered each type simultaneously; all made by the player's identity.

**Status card interaction with labeled abilities:**

- If identity has a status card canceling ANY of the labeled types: **entire ability** (except costs) is canceled.
- Identity is NOT considered to have attacked, defended, or thwarted.
- Each status card on identity that cancels any of the labeled types is **removed**.
  - E.g., "(attack/thwart)" ability while stunned AND confused: both status cards removed; ability canceled.

---

## IDENTITY EXTENSIONS

The following card types are considered **extensions of the player's identity** (actions/abilities resolve AS IF performed by identity):

- **Events** — attacks, thwarts, defenses, action abilities, triggered abilities
- **Resources** — attacks, thwarts, defenses, triggered abilities
- **Upgrades** (unless attached to a different friendly character) — all of the above

The following are **NOT** extensions of identity:

- **Allies**
- **Encounter cards** (optional or forced)
- **Player Side Schemes**
- **Supports**
