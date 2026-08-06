---
name: marvel-champions-learn-to-play
description: Fast rules primer for Marvel Champions — the shape of a round, what a player may do on a turn, and the five villain-phase steps, with references for setup, encounters, statuses, and deckbuilding.
metadata:
  game: "Marvel Champions: The Card Game"
  role: "rules primer"
  scope: "summary depth, core set"
  version: "1.1"
---

Marvel Champions is a **cooperative** card game for **1–4 players**. Each player takes the role of
one Marvel hero, playing as that character and their alter-ego. Players work together to defeat a
villain — controlled by the game, not by a player — before the villain completes their evil scheme.

This file is the fast primer. It carries the shape of a round and nothing else; everything past
that lives in a reference you fetch on demand.

## Scope

- This is **not the harness.** How to actually execute a play against a live table — which
  game-service tool, which group id, which argument — is `marvel-champions-play`. Nothing here
  tells you what to call.
- This is **not the authority.** For a keyword, a timing window, or a card interaction,
  `marvel-champions-rules-reference` wins. This skill is a summary that trades precision for
  speed; where the two differ, it is this one that is wrong.
- This **is** the primer. Load it when you need the shape of a round quickly, or when you are new
  to the game and need the vocabulary before the rules reference will make sense.

---

## Win / Loss Conditions

| Condition                                                               | Result           |
| ----------------------------------------------------------------------- | ---------------- |
| Players reduce the **final villain stage** hit points to zero           | **Players WIN**  |
| Villain accumulates threat ≥ target threat on the **final scheme card** | **Villain WINS** |
| **All players** are eliminated (hit points reach zero)                  | **Villain WINS** |

---

## Key Concepts

**The Golden Rule.** If card text directly contradicts the rulebook, **card text takes precedence**.

**Per Player Symbol (👤).** The 👤 symbol next to a value multiplies that value by the **number of
players who started the scenario**.

**Ready and Exhausted.** Cards **enter play ready** (upright). To use some powers and abilities the
card must **exhaust** (rotate sideways). An exhausted card **cannot exhaust again** until readied.

**"In Player Order".** The **first player acts first**, then each other player clockwise.

**Villain Stages.** The villain is a **sequential deck of stage cards**, each with a stage number in
its upper-right corner. Reducing a stage's hit points to zero **advances to the next stage**;
defeating the **final stage** wins the game.

---

## Round Structure

Each round consists of two phases, in order:

1. **Player Phase** — players take turns in player order. After every player has taken a turn, each
   player discards down to hand size, draws back up to hand size, and readies **all** their cards.
2. **Villain Phase** — the five steps below.

After the villain phase, pass the first player token **clockwise** and begin the next round.

### A Player's Turn

On their turn, a player may do the following **in any order** and **as many times as desired**,
except where noted:

| Option                              | Cost / limit                                                     |
| ----------------------------------- | ---------------------------------------------------------------- |
| **Change form** (hero ↔ alter-ego)  | **Once per turn.** Damage, upgrades, tokens, and statuses remain. |
| **Play a card**                     | Pay its resource cost. Max **3 allies** in play per player.       |
| **Use a basic power**               | Exhaust the hero or alter-ego.                                   |
| **Use an ally**                     | Exhaust it; it then takes consequential damage.                   |
| **Trigger an Action ability**       | Pay the cost shown before the **→**.                              |
| **Ask another player to Act**       | They decide; they may also volunteer.                            |

Basic powers, by form:

| Power              | Form      | Effect                                                                                 |
| ------------------ | --------- | -------------------------------------------------------------------------------------- |
| **Basic Attack**   | Hero      | Deal damage = ATK value to one eligible enemy (villain or minion)                      |
| **Basic Thwart**   | Hero      | Remove threat = THW value from one scheme of choice                                    |
| **Basic Defense**  | Hero      | Exhaust to prevent damage = DEF value from an attack (can defend self or another hero) |
| **Basic Recovery** | Alter-Ego | Heal HP = REC value (cannot exceed max HP)                                             |

### The Villain Phase — Five Steps

1. **Place threat.** Equal to the main scheme's **acceleration field**, +1 per acceleration side
   scheme in play.
2. **Villain and minion activations.** The villain activates **once per player**, in player order,
   then each minion engaged with that player activates. A player in **alter-ego** form is schemed
   against; a player in **hero** form is attacked. The villain draws a **boost card** for each of
   its own activations; minions never do.
3. **Deal encounter cards.** One facedown card to each player in player order, +1 per hazard side
   scheme in play.
4. **Reveal encounter cards.** One at a time, in player order, resolving each by its card type.
5. **Pass the first player token** clockwise and end the round.

---

## References

Load exactly the one you need — these are fetched by name, not inlined.

| Reference                                                              | Load when...                                                                                                              |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| [references/setup.md](references/setup.md)                             | Putting a scenario on the table — the 14 setup steps in order, and what expert mode changes.                              |
| [references/player-turn.md](references/player-turn.md)                 | Resolving a turn in detail — playing cards, resource costs and types, basic powers, allies, Action abilities, end of phase. |
| [references/villain-phase.md](references/villain-phase.md)             | Resolving a villain phase in detail — boost cards, scheme vs. attack activations, encounter reveal, surge, obligations, nemesis side schemes. |
| [references/schemes-status-and-damage.md](references/schemes-status-and-damage.md) | Threat advancing a scheme, the three side-scheme icons, how damage applies to each target, or a Stunned / Confused / Tough question. |
| [references/card-types.md](references/card-types.md)                   | Asking what a card type is or does on entering play, or what aspects and basic cards are.                                 |
| [references/deck-customization.md](references/deck-customization.md)   | Building or checking the legality of a player deck.                                                                       |
| [references/quick-reference.md](references/quick-reference.md)         | You want the at-a-glance tables — stat abbreviations, phase flow diagrams, resource / side-scheme / boost icons, status effects. |

For scenario contents, hero decklists, nemesis sets, or any specific card, do not look here — query
`search_cards_marvel_champions`. This skill deliberately carries no card data, because the plugin
loads scenarios far beyond the core set.
