# Marvel Champions — Encounter Deck & Reveal

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## ENCOUNTER DECK

### Contents

Attachments, environments, minions, side schemes, treacheries (and obligations, shuffled in during setup).

### Order

Cannot be changed unless instructed by a game step, function, or card ability.

### Empty Deck

- When empty: **immediately** shuffle encounter discard pile into a new encounter deck; place **1 acceleration token** next to main scheme.
- If both deck AND discard pile are simultaneously empty: infinite acceleration tokens -> **players lose**.

### Discarding Cards from the Encounter Deck (via ability)

- "Discard X cards from the encounter deck" or "until a card with [criteria] is discarded": stop when condition met OR deck empties.
- If deck empties: ability is considered **fulfilled**. Do NOT continue with the newly shuffled deck.

### Facedown Encounter Cards

- Cards dealt to players or given as boost cards: facedown and **out of play**.
- Cannot be targeted by "find" instructions.
- Cannot be found by search abilities.
- Not considered in play (even if physically in a play area).

---

## DEALING ENCOUNTER CARDS (Villain Phase Step 3)

- Deal **1 facedown encounter card** to each player.
- Deal **1 additional card** per hazard icon on cards in play; additional cards dealt in **player order** (first additional to first player, second to second player, etc.).
- If a player is dealt an encounter card during step 3 or 4: that card is added to the queue for that same step.

---

## REVEAL PROCEDURE (Villain Phase Step 4)

First player reveals all their encounter cards (one at a time, in dealt order), then each other player in player order. Repeat until no dealt encounter cards remain.

### Step-by-Step Reveal

```
Step 1: Turn card faceup.

Step 2: Based on card type:
  Attachment  -> enters play attached to the game element specified in its text
  Environment -> enters play in villain's play area
  Minion      -> enters play in revealing player's play area; engages that player
  Obligation  -> enters play in revealing player's play area
                If card specifies a player to give it to: that player is considered to be revealing it
                If cannot be given to specified player: ignore ability, remove from game,
                                                         reveal an additional encounter card
  Side Scheme -> enters play in villain's play area
  Treachery   -> place on table in front of revealing player (NOT in play)
  Other       -> place on table in front of revealing player (NOT in play)

Step 3: Resolve each "When Revealed" ability (including keyword-triggered ones like Surge, Hinder, Incite).

Step 4: If treachery, discard it.
```

### Reveal from Other Areas

If a card ability instructs a player to reveal an encounter card from the encounter deck or any other game area: same resolution procedure applies.

---

## ENCOUNTER SETS

- A grouping of encounter cards.
- Four types: scenario-specific, modular encounter sets, Standard set, Expert set.
- Encounter sets with the same name but **different set icons** are considered **distinct sets**.

### Standard Set

- Added to most scenarios.
- NOT a modular encounter set; cannot be selected when a scenario requires players to choose a modular set.

### Expert Set

- Added during expert mode.
- NOT a modular encounter set; cannot be selected as a modular set.

### Modular Encounter Set

- Can be added to/removed from nearly any scenario.
- If added to a scenario: entire set included (individual cards cannot be excluded unless scenario rules state otherwise).
- Multiple modular sets can be added, but this dilutes the encounter deck.

---

## SEARCH & FIND

### Search

- Player is permitted to look at each card in the searched area.
- If multiple cards satisfy criteria: player chooses among them.
- Cards being searched are NOT considered to leave the searched area.
- After any portion of a deck is searched: **shuffle that entire deck** upon completion.
- "Search [their] collection": player looks through all Marvel Champions cards outside current game for the specified card; becomes its owner until game ends.

### Find

- Player searches each game area where the card could be found (play area, set-aside, player deck, discard pile, encounter deck, etc.).
- Players should not unnecessarily search areas where they know the card is NOT.
- **Excluded from "find":** facedown encounter cards in any in-play game area, victory display, cards removed from the game.
- "Find and reveal" a minion already in play: player engages it; resolve When Revealed + keywords; retains attachments/tokens; NOT entering play; considered to engage that player (unless already engaged).

---

## DISCARD PILE

- Each player has their own; encounter deck has its own.
- **Open information** — may be looked at by any player at any time.
- Order cannot be changed unless a card ability instructs it.
- Any ability that would shuffle a discard pile of **zero cards** into a deck: does not shuffle the deck.
- If multiple cards discarded from a hand or in-play area by a single effect: place in discard pile in **any order**.
- If multiple cards discarded from a deck by a single effect: place in discard pile **one at a time** (without changing order); considered simultaneous; responses resolve after all discards made.
- If player looks at cards from top of a deck and discards some: those are considered discarded from **top of that deck**.

---

## OBLIGATION RULES (REVEAL CONTEXT)

- Shuffled into encounter deck during setup.
- If obligation specifies a player (e.g., "Give to the Peter Parker player"): place in that player's play area.
- If that player cannot receive it: ignore ability, remove from game, reveal additional encounter card.
- If obligation does not specify a player: place in the revealing player's play area.
- Only the player with the obligation in their play area can trigger abilities or pay costs on it.
- If drawn from player deck: place in that player's play area (no replacement draw unless refilling to hand size).
