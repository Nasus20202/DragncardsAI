# Marvel Champions — Glossary A–D

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## ABILITY

Game text on a card explaining what it does or can do.

- Card abilities only interact with **in-play** cards unless the ability specifically refers to an out-of-play area.
- If an ability specifies one or more targets, it can only be initiated if **at least one valid target exists**.
- When an ability has multiple sentences, read the **entirety** first to check for alteration effects, then resolve **one sentence at a time**.
- Player card abilities **cannot resolve during game setup** unless prefaced by a "Setup" timing trigger.

**Mandatory ability types** (must resolve): Constant, Setup, When Revealed, When Defeated, Forced Action, Forced Interrupt, Forced Response, Boost, Keywords.

> If one of these uses the word "may," the part following "may" is optional.

**Optional ability types** (controller decides): Action, Interrupt, Response, Resource.

- The **controller of the card** determines whether to use optional abilities.
- Any player can use optional abilities on **encounter cards**, with exceptions:
  - Only the player who controls a player card with an attachment using "you"/"your" can trigger abilities or pay costs on that attachment.
  - Only the player with an **obligation** in their play area can trigger abilities or pay costs on that obligation.

### Constant Abilities

- Non-keyword ability with **no bold timing trigger**.
- Active as soon as the card **enters play**; remains active while in play.
- Conditions denoted by "during," "if," or "while" — effects are active whenever the condition is met.
- Multiple instances of the same constant ability each affect the game **independently**.
- Constant abilities have **timing priority** over all triggered abilities.

### Triggered Abilities

- Indicated by a **bold timing trigger followed by a colon** and the ability text.
- Unless prefaced by "Forced," all interrupt and response abilities are **optional**.
- If the bold timing trigger contains "Hero" or "Alter-Ego," the ability can only be used if the triggering player is in the **specified form**.
- If quotation marks are used around a timing trigger, the quoted text refers to **other abilities with that trigger**, not itself a trigger.

---

## ACCELERATION ICON (⬆) / ACCELERATION TOKEN

**Acceleration Icon:** During step 1 of the villain phase, place X additional threat on the main scheme, where X = number of acceleration icons in play. Removed from play by defeating the encounter card it is printed on.

**Acceleration Token:** Functionally equivalent to acceleration icons (but not considered icons). Placed next to the main scheme.

- Enters play when: encounter deck is empty (place 1 token), or a card effect instructs it.
- Tokens on cards other than the main scheme still add threat; removed when that card leaves play.
- Tokens **on the main scheme cannot be removed**; not discarded when the main scheme advances.
- Acceleration tokens ≠ acceleration icons (and vice versa).

---

## ACTION

A type of triggered ability. Players may trigger action abilities during **their own turn**, or by request during other players' turns.

- Can only trigger on cards they **control** or **encounter cards** (not obligations in other players' play areas).
- Each **"Forced Action"** must be resolved before the player phase can end; can be triggered at any valid action timing.
- If a forced action has an unpayable cost or no valid targets, the phase can end without it resolving.

---

## ACTIVATION

Two types: **attack activation** and **scheme activation**. Whenever an enemy attacks or schemes, it has activated.

- Villain activates **once per player** in player order during step 2 of the villain phase.
- Each **minion engaged with a player** activates against that player after the villain activates.
- Each villain activation gives the villain **one boost card**.
- Card abilities can also cause enemies to activate; these count as activations.
- Multiple simultaneous activations: resolve villain's first, then minions in your choice of order.
- If an activating minion **leaves play**: that activation ends immediately.
- An effect that initiates an activation is resolved after that activation **fully resolves**.
- Nested activations: new activation resolves **after** the current one finishes.

---

## ACTIVE PLAYER

The player taking their turn during the player phase.

---

## ALLY

A player card type representing friends, supporters, or companions.

- Remains in play until a card ability or game effect causes it to leave play. Defeated (0 or fewer HP) → discarded.
- During a player's turn, they may use **any number of allies** to attack or thwart (each must exhaust).
- After attacking or thwarting: deal **consequential damage** (⬤) equal to icons beneath its ATK or THW field.
  - Exception: if an ally attempts to attack while **stunned** or thwart while **confused**, it does **not** take consequential damage.
- **Any player** may exhaust an ally they control to defend against an attack. All damage is then dealt to the ally.
- Attacks, thwarts, defenses, action abilities, and triggered abilities from allies are **not** considered performed by the controlling player's identity.

**Ally Limit:** Maximum **3 allies** per player in play at any time. May play/put into play beyond the limit, but must immediately discard down to 3. This occurs **before** abilities that resolve upon entering play.

---

## ALTERATION EFFECT

Modifies the resolution of a preceding ability.

| Type                                   | Keyword         | Rule                                                                                                                                                 |
| -------------------------------------- | --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Additional**                         | "additional"    | Modifier to an ability or game state; resolves simultaneously with the ability it modifies                                                           |
| **Already**                            | "already"       | Checks if a specific condition is already met before the preceding ability attempts to resolve; if met, the "already" effect resolves instead        |
| **Each Time**                          | "each time"     | Temporarily halts a resolving ability when a condition is met; the "each time" effect resolves in its entirety, then the preceding ability continues |
| **This/That Attack/Activation/Thwart** | "this" / "that" | Modifier to that specific instance of an attack, activation, or thwart                                                                               |

> **Note:** If "this/that activation/attack/thwart" is part of a _condition_ for an effect, it is **not** an alteration effect.

---

## "AND"

Indicates two or more effects within an ability resolve **simultaneously**.

- Individual effects connected by "and" are **not dependent** on each other — resolve as much as possible.
- Each effect connected by "and" can be **canceled or prevented independently**.

---

## ASPECT CARD

Cards belonging to the **Aggression, Justice, Leadership, and/or Protection** aspects (and 'Pool).

- When building a player deck, choose one of five aspects; the deck (excluding identity-specific cards) is customized with that aspect's cards and/or basic cards.
- A card's aspect is printed at the bottom of the card in its deckbuilding classification area.

---

## ASSAULT

When a character makes a **basic thwart against a scheme** with the assault keyword, that character uses its **ATK instead of THW**. See: keywords.md (Assault).

---

## ATTACHMENT

An encounter card type. When an attachment enters play, it attaches to another card or game element.

- May modify the attached character's ATK, SCH, and/or THW values.
  - "SCH/THW" modifier: modifies SCH for villains/minions; modifies THW for heroes/allies.
  - If the attachment modifies a value the attached character doesn't have (or has –), that modifier is **ignored**.
- When an attachment on a player card uses "you"/"your," it refers to the **attached player card's controller**.
  - Only the controller of the card to which the attachment is attached can trigger abilities or pay costs on that attachment.

**Attach To:** If a card uses "attach to," it must be placed **beneath and slightly overlapped by** the specified game element as it enters play.

- "Attach to" is checked for legality **when attaching only**, not thereafter.
- Once attached, it remains in play until the attached element leaves play (discarding the attachment) or an ability causes the attached card to leave play.
- An attached card **exhausts and readies independently** of the game element it's attached to.
- The "attach to" phrase on a card is **not resolved** if another ability causes that card to attach to a specific game element.

---

## ATTACK (ENEMY ACTIVATION)

An attack is a type of enemy activation. The enemy targets a specific player, then resolves the attack against that player.

- Enemy attacks are always initiated against both a **player** and a **character**.
  - Normally the attacked character is the player's hero; abilities can redirect to alter-ego or an ally.
  - In all cases, the **player is still considered attacked**.
  - If a different character defends, that character becomes the **new target**.
  - If a different player defends, that player becomes the **new target**.

**Steps to resolve:**

1. **Boost card** — Give villain or villainous minion one facedown boost card. (Skip for non-villainous minions.)
2. **Declare defender** — The target player may exhaust a hero or ally to defend. If a different player defends, they become the target player.
3. **Resolve boost cards** (one at a time, in order dealt):
   - Flip faceup → resolve any "Boost" ability (only text beneath divider line) → increase ATK by boost icons → discard.
4. **Deal damage** equal to the attacking enemy's modified ATK:
   - **Hero basic defense** → damage reduced by DEF; remaining damage dealt to hero. Hero keeps tough if DEF reduces damage to 0.
   - **Ally defends** → all damage dealt to the ally. If ally leaves play before damage, attack is undefended and the ally's controller's identity becomes the target.
   - **No defender (undefended)** → all damage dealt to the targeted character.
5. **Abilities trigger in order:**
   - a. Retaliate X (if attacked character is still in play)
   - b. Forced abilities: "after [character] attacks [and damages/defeats] [you/an ally]," "after [character] is attacked," "after [character] defends [and takes no damage]," "after [character] [takes/deals] damage"
   - c. Non-forced abilities with the above triggers

> If an enemy attack **ends before damage is dealt**: defender-trigger abilities resolve, but attacker-trigger abilities do not.

---

## ATTACK (PLAYER ABILITY TYPE)

Ways a player attack can occur:

1. **Basic attack**: Hero or ally exhausts and uses ATK. Can only initiate if there is an enemy that can be attacked, **or** if that character is stunned.
2. **Triggered ability labeled (attack)**: Resolving it counts as an attack. Hero does **not** exhaust unless specified. A single labeled attack is one attack even if it deals multiple damage instances.
3. **"Make the following X attacks in order"**: Each instance is a **separate attack**.

**Increasing damage on attack abilities:** When an attack ability's damage is increased, each instance **not using the word "additional"** is increased by the specified amount.

**Multiple target attacks:** When an attack targets multiple enemies, the attacker is considered to have attacked **each** of those enemies. Each attacked enemy with retaliate X still in play deals its retaliate damage to the attacker.

**Resolution order (after attack):**

1. Retaliate X (if attacked character was not defeated)
2. Forced abilities: "after [character] attacks [and damages/defeats] [an enemy/a minion]..." and "after [character] is attacked..."
3. Non-forced abilities with the above triggers
4. Consequential damage (for allies)

---

## ATTACKS AGAINST ALLIES

When a villain or minion attacks an ally directly:

- The player who controls the ally is the **attacked player**.
- "Attacks you" abilities resolve against the attacked player.
- Boost abilities referring to "you" refer to the player who controls the attacked ally.
- Players may defend normally.
- If the attack has **overkill** and defeats an ally (attacked or defending): excess damage is dealt to the **identity of the player who controlled the defeated ally**.

---

## BASE VALUE

A defined value **before modifiers are applied**. In most cases, also the printed value.

---

## BASIC CARD

Cards in the "Basic" classification — not associated with a specific identity or aspect. May be included in any player deck. Basic cards are **not** aspect cards.

---

## BASIC POWER

| Power    | Abbrev. | Function                                     | Who Has It                        |
| -------- | ------- | -------------------------------------------- | --------------------------------- |
| Attack   | ATK     | Basic attack; deal damage equal to ATK       | Heroes, allies, villains, minions |
| Thwart   | THW     | Basic thwart; remove threat equal to THW     | Heroes, allies                    |
| Defense  | DEF     | Basic defense; reduce incoming damage by DEF | Heroes only                       |
| Recovery | REC     | Basic recovery; heal damage equal to REC     | Alter-egos only                   |
| Scheme   | SCH     | Basic scheme; place threat equal to SCH      | Villains, minions                 |

A value of **dash (–)** means that character **cannot exhaust to use that power**.

---

## BOOST / BOOST ICON (▼)

- Each time the villain attacks or schemes, give it **one facedown boost card** from the encounter deck.
- Minions with **villainous** keyword also get a boost card when they activate.
- Each boost card is turned faceup one at a time during the activation. Boost icons increase the enemy's ATK (if attacking) or SCH (if scheming) for that activation.
- A **star icon** (★) in the boost field indicates a "Boost" ability in the text box (text beneath the divider line). The star icon itself is **not** a boost icon.
- Only text **beneath the divider line** is active on a boost card. Damage from a boost ability is **not** considered damage from the activation.
- Multiple boost cards: icons are **cumulative**; all "Boost" abilities resolve.
- After applying a boost card, **discard it**.
- Boost card dealt outside own activation: remains **facedown** until the enemy activates. A villain or villainous minion still gets **another** boost card at the start of its activation.

---

## CANCEL

Some card abilities can cancel card or game effects.

- Cancel abilities **interrupt the initiation of effects** and prevent them from resolving.
- The ability (apart from its effects) is still regarded as initiated; costs are still paid.
- If an **event card's** effects are canceled: card is still considered played, then discarded.
- If a **treachery card's** effects are canceled: card is still considered revealed; placed in encounter discard pile.
- Cancel effects are a **subtype of replacement effect** (the canceled effect is replaced by no effect).
- Abilities **dependent on the canceled effect cannot trigger** (the canceled effect is not considered to have occurred).
- "When Revealed" abilities on **villain and main scheme cards cannot be canceled**.

---

## "CANNOT"

See: golden-rules.md ("Cannot" Is Absolute).

---

## CARD TYPES

**Player card types:** Ally, Event, Identity, Player Side Scheme, Resource, Support, Upgrade.

**Encounter card types:** Attachment, Environment, Main Scheme, Minion, Obligation, Side Scheme, Treachery, Villain.

**If a card changes its card type:** it loses all other card types and functions as the new type. Cards attached to it remain attached, but only abilities referencing the **new type** remain active.

- An ally changed to a minion **engages its controller** and does not take consequential damage after attacking or scheming.
- When a player changes a minion to an ally, **that player takes control** of that ally.

---

## CHARACTER

Identities (heroes and alter-egos), allies, villains, and minions are all **characters**.

---

## CHOOSE (GAME ELEMENT)

"Choose a [game element]" — the player **resolving the ability** makes the choice.

- If a player card ability requires choosing targets with no valid targets: the ability **cannot be initiated**.
- Multiple targets required by same player: simultaneously choose as many as available, up to the specified number.
- "Any number" of targets: **does not successfully resolve if zero targets are chosen**.

## CHOOSE (OPTION)

Some abilities instruct a player to choose between multiple options.

- **Encounter card options**: cannot choose an option requiring one or more targets if there are no valid targets for that option.
- **Player card options**: cannot choose an option that has a cost the player cannot pay, or that requires one or more targets with none valid.

---

## CLASSIFICATIONS

| Classification        | Description                                                        |
| --------------------- | ------------------------------------------------------------------ |
| Identity-specific     | Cards belonging to an identity's set                               |
| Aspect                | Cards in Aggression, Justice, Leadership, Protection, and/or 'Pool |
| Basic                 | Cards not tied to a specific identity or aspect                    |
| Scenario-specific     | Cards belonging to a scenario's set                                |
| Modular encounter set | Cards belonging to a modular set                                   |
| Campaign-specific     | Cards usable only during a specific product's campaign             |
| Standard              | Cards added to most scenarios                                      |
| Expert                | Cards added to scenarios in expert mode                            |

---

## CONFUSE / CONFUSED

A **status** that cancels a character's next scheme or thwart.

- **Steady** keyword: confused only if it has **two** confused status cards.
- A character that "cannot be confused": cannot have confused status cards placed on it.
- If a **confused identity or ally** attempts to thwart or use a thwart ability:
  - Discard the confused status card instead; costs (including exhausting) **must still be paid**.
  - A confused character **can** attempt to thwart even with no valid target.
- If a **confused villain or minion** would scheme: discard the confused status card instead.
- The thwart/scheme was replaced by removal of the confused card; the character is **not** considered to have thwarted or schemed.

---

## CONSEQUENTIAL DAMAGE (⬤)

- After an ally **attacks**: deal ⬤ icons beneath ATK field in damage.
- After an ally **thwarts**: deal ⬤ icons beneath THW field in damage.
- Consequential damage is dealt **after** resolving abilities triggered by the ally attacking or thwarting.
- If the target of an ally's basic power **leaves play** before the ally deals ATK damage / removes THW threat:
  - The ally does **not** take consequential damage (but still exhausts).
  - The ally is **not** considered to have attacked or thwarted for other ability purposes.

---

## COPY

A copy of a card is defined by **title**. A second copy is any card sharing the same **title and subtitle (if any)**, regardless of card type, text, or artwork.

---

## COST

A card's resource cost must be paid to play it; some abilities have costs that must be paid to use them.

- A **cost arrow (→)** distinguishes cost from effect: "pay cost → resolve effect."
- A resource cost with the **per-player icon (👤)** is multiplied by the number of players who **started** the scenario; the multiplied value is not separately reduced.
- To pay a resource cost: generate resources by discarding cards from hand or using "Resource" card abilities.
- **Excess resources** generated are **lost** after paying.
- Multiple costs for a single card/ability must be **paid simultaneously**.
- A cost **cannot be paid** if the effect requires one or more targets with none valid.
- When paying a cost: use cards/game elements **you control** (exceptions: "choose" targets, "friendly" targets).
- If a cost requires a game element **not in play**: only use elements from your **own out-of-play areas**.
- "Any number" or "up to" game elements: requires a **minimum of one**.
- **Additional costs**: all additional costs must be paid simultaneously with the original cost; cannot pay individually.
- If **dealing damage** is a cost: cost is paid **even if some/all damage is prevented**.
- If **taking damage** is a cost: cost is **not** paid unless **all** damage was taken (if any is prevented, cost is not paid).

---

## DAMAGE

Damage reduces a character's hit points. 0 or fewer remaining HP → **defeated**.

- **Identity/Villain**: tracked by a **hit point dial**; reduce by damage taken.
- **Ally/Minion**: tracked by **damage tokens** placed on the character.

**Key distinctions:**

- When the amount of damage an effect **deals** is modified → the amount **taken** is similarly modified.
- When the amount of damage a character **takes** is modified (e.g., prevented) → the amount **dealt** is **NOT** modified.

**Resolution order:** See timing.md (Damage Resolution Order).

---

## DASH (VALUE)

A value presented as a dash (–) indicates that value **cannot be used**.

- Cost "–": card **cannot be played**; can only enter play by other means.
- Power (ATK, DEF, REC, SCH, THW) "–": character **cannot exhaust to use that power**.
- Referenced as a value by a game step or ability: treated as an **unmodifiable 0**.

---

## DEFEAT

If a character has 0 or fewer remaining hit points, or if a side scheme has no threat on it, it is **defeated**.

- **Ally, minion, or side scheme** → **discarded**.
- **Identity or villain stage** → **removed from the game**.

---

## DEFEND / DEFENSE

During an enemy attack, a player may defend using cards they control. Only **one player at a time** can defend against an enemy attack.

**Hero basic defense:** Hero exhausts; damage reduced by DEF; remaining damage dealt to hero. Declaring a hero the defender via card ability = making a basic defense.

**Ally defense:** Ally exhausts; all damage dealt to the ally. If the defending ally leaves play before damage is dealt: attack is considered undefended; identity of that ally's controller becomes the target.

**Defense-labeled ability (e.g., "Hero Interrupt (defense)"):**

- Player's identity becomes the defender (if no defender already exists). Identity is considered the defender **as soon as the ability begins resolving**.
- Playing a defense-labeled ability is **not** a basic defense; hero does NOT reduce damage by DEF.
- Hero does **not** exhaust (unless specified).
- A player may resolve **any number** of defense abilities during an attack.
- Once a player resolves a defense-labeled ability: **other players cannot** resolve defense-labeled abilities for that attack.
- Defense-labeled abilities can be played when an **ally is defending** — in this case, the identity does NOT become the defender.

**Cross-player defense:** If a player defends an attack targeting a different player, the defending player becomes the **new target**.

- "you" in "when [enemy] attacks you" = player against whom the attack **initiated**.
- "you" in "after [enemy] attacks you" = player whose character **defended**.
- "you" in constant or boost abilities = the **defending player**.

**Undefended:** No character defends, OR a defending ally is defeated before damage is dealt.
