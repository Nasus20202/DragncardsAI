# Marvel Champions — Ownership, Control & Play Areas

**Source:** Rules Reference v1.7 | **Referenced by:** SKILL.md

---

## OWNERSHIP

- **Owner** = the player whose deck contained the card at the start of setup.
- **Scenario** = owner of the encounter deck and each encounter card.
- Identity cards: owned AND controlled by the player playing as that identity.
- Player owns all cards in their own out-of-play areas (hand, deck, discard pile).

### Special Ownership Cases

- **Linked cards:** when a player takes control of a linked card, that player becomes its owner.
- **Campaign/scenario-specific player cards with a player card back:** when a player takes control, that player becomes the owner until the game ends or another player takes control.
- **"Search [their] collection":** that player becomes the card's owner until end of game.

---

## CONTROL

- Cards enter play under their **owner's control**.
- Encounter cards: under control of the **scenario**.
- Upgrades attached to a card controlled by a player other than the upgrade's owner: **controlled by that other player**.

### Control Remaining Constant

- Control of a card remains constant unless an ability explicitly causes it to change.
- "You control" / "player controls": refers only to cards **currently in play** under that player's control.

### When a Character Changes Control (In Play)

- Retains same state: ready/exhausted, damaged/not, etc.
- Moved to new controller's play area.
- Upgrades on that card also change control to the same new controller.

### When Control Change Ends

A control change reverts when:

1. The ability that changed control ceases to be in effect (e.g., attachment removed) -> reverts to owner's control.
2. The card **leaves play** -> goes to owner's equivalent out-of-play area (hand/deck/discard) or removed from game if owner eliminated.
3. The card is an **event that was played** -> goes to owner's discard pile.
4. The card is **discarded from a player's hand** -> goes to owner's discard pile.

---

## PLAY AREAS

### Player's Play Area

Contains:

- Identity card + hit point dial
- Hand of cards
- Player deck
- Discard pile
- Ally, upgrade, support cards in play
- Engaged minions
- Obligations given to that player
- Facedown encounter cards dealt to that player

### Villain's Play Area

Contains:

- Villain deck + hit point dial
- Main scheme deck
- Encounter deck
- Encounter discard pile
- Environment cards in play
- Side scheme cards in play
- Attachment cards on cards in villain's play area

### Important Clarifications

- Minion cards engaged with a player -> in that **player's** play area (NOT villain's).
- Obligation cards given to a player -> in that **player's** play area (NOT villain's).
- Attachment on card in villain's play area -> in villain's play area.
- Attachment on card in player's play area -> in player's play area (NOT villain's).
- A card cannot be in more than **one** play area at a time.
- Player cards normally cannot be played into another player's play area (unless ability states otherwise).

---

## IN PLAY vs. OUT OF PLAY

### In Play (text active; can affect game)

- Faceup side of player's identity card.
- Faceup ally, support, upgrade cards that have entered play.
- Faceup top card of villain deck and faceup top card of main scheme deck.
- Faceup attachment, environment, minion, obligation, side scheme cards that have entered play.
- A double-sided card: the **faceup** side is in play.

### Out of Play (text inactive)

- Player's hand, deck, discard pile.
- Encounter deck, encounter discard pile.
- Unrevealed cards in villain deck and main scheme deck.
- Facedown encounter cards dealt to players.
- Facedown cards attached to in-play cards.
- Cards removed from the game or set aside.
- Facedown side of a double-sided card.

### Key Rules

- Card abilities only interact with, and can only target, cards **in play** (unless ability specifically references an out-of-play area).
- Event cards and treachery cards implicitly resolve from an out-of-play area (per their card type rules).

---

## ENTERS PLAY / LEAVES PLAY

### Enters Play

Any transition from an out-of-play area to a play area.

- Methods: playing a card, putting a card into play via ability, revealing from encounter deck.

### Leaves Play

Any transition from a play area to an out-of-play area.

- Methods: defeating a character, discarding from play, placing in victory display, removing from game.
- When a card leaves play:
  - **Discard** each card attached to or tucked under it.
  - **Discard** each boost card given to it.
  - **Return** each token and status card on it to the supply.
- When a card leaves play: **no memory of previous state**; considered a new copy of the card.

### Play vs. Put Into Play

- **Playing**: pay cost; observe play restrictions; card is played.
- **Put into play**: bypasses cost AND play restrictions; card is NOT considered to have been played; resource cost ignored.
- Unless stated otherwise by the "put into play" effect: card must enter play in a valid play area/state.

---

## PLAYER ELIMINATION

When a player is eliminated (identity defeated or otherwise):

```
1. Pass first player token to next clockwise player (if they held it).
2. Each engaged minion engages next clockwise player
   - Retains tokens, attached cards, boost cards, tucked cards, status cards.
3. For each card in eliminated player's play area NOT owned by that player:
   - Attachment with permanent keyword: resolve "attach to" or remove from game.
   - Non-attachment permanent: remove from game.
   - All other cards: place in owner's discard pile.
4. Each card owned by eliminated player -> their discard pile.
5. Remove the eliminated player's play area and ALL game elements within it
   (hand, deck, discard pile, cards in play, hit point dial, etc.) from the game.
```

- Remaining players continue; eliminated player wins/loses with group.
- All players eliminated -> **players lose**.
- If eliminated mid-ability: resolve entire ability.
- "Players in game": eliminated players ignored **except** for per-player icon.

---

## REMOVED FROM THE GAME

- Set aside; no interaction with the game for duration of removal.
- If no specified duration: removed until end of game.
- "Removed from the game" = out-of-play state.
- Excluded from "find" instructions.

---

## SET ASIDE / SET-ASIDE AREA

- Out of play; no interaction until referenced by scenario/card ability.
- Used for: nemesis sets, linked cards, permanent cards (before being put into play), cards set aside by abilities.

---

## VICTORY DISPLAY

- Out-of-play game area shared by all players.
- Cards in the victory display follow standard out-of-play rules.
- Some scenarios/campaigns count victory points (value = X in Victory X keyword).

---

## TUCK

- Tucked card placed **faceup** under another card.
- Tucked cards: NOT in play; NOT considered "attached."
- When host card leaves play: each tucked card is discarded.
