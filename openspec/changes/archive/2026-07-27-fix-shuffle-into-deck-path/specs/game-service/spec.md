## ADDED Requirements

### Requirement: Shuffle-into-deck returns a card to its own deck
The Game Service SHALL, for the `shuffle_into_deck` action, move the named card into the group identified by that card's own `deckGroupId` and then shuffle that group. The caller SHALL NOT name a destination group; the destination is derived from the card.

The emitted DragnLang SHALL read `deckGroupId` as a **value**, using dotted `$GAME.cardById.<instance_id>.deckGroupId` access. It SHALL NOT read it through a `/`-prefixed path literal: DragnCards evaluates a string beginning with `/` to the path list it denotes rather than to the value stored at that path, so such a literal yields a list where a group id is required and the engine rejects the move with `Group not found: cardById<instance_id>deckGroupId`.

`/`-prefixed path literals remain correct as the *target* of a write operation such as `SET` or `INCREASE_VAL`, where the path list is what those operations expect.

The action SHALL accept an optional `player_n` and, when it is supplied, inject `player_ui.playerN` into the DragnCards request, so that plugin automation triggered by deck insertion can resolve `$PLAYER_N`. Without it a card returning to a `playerNDeck` is rejected with `Variable $PLAYER_N is undefined`. `player_n` remains optional because shared decks need no player context.

#### Scenario: Card is moved into its own deck and the deck is shuffled
- **WHEN** a client sends `POST /games/{id}/actions/shuffle_into_deck`, or invokes the `shuffle_into_deck` MCP tool, for a card held in a player's hand, supplying that player as `player_n`
- **THEN** the action SHALL complete with a null `error`
- **AND** the card SHALL afterwards be in the group named by its `deckGroupId`
- **AND** that group SHALL contain one more stack than before
- **AND** that group's stack order SHALL have been shuffled

#### Scenario: Deck group is read as a value, not as a path
- **WHEN** the Game Service translates a `shuffle_into_deck` action
- **THEN** the deck-group expression bound for the subsequent move and shuffle SHALL be a dotted `$GAME.` read
- **AND** it SHALL NOT be a `/`-prefixed path literal

#### Scenario: Player context is forwarded to deck-insertion automation
- **WHEN** a `shuffle_into_deck` action supplies `player_n`
- **THEN** the emitted request SHALL carry `player_ui.playerN` set to that player
- **AND** when `player_n` is omitted the request SHALL carry no `player_ui`
