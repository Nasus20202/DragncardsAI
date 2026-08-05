## ADDED Requirements

### Requirement: Prebuilt deck loading selects a player seat
The Game Service SHALL accept the acting player seat when loading a prebuilt deck, through both `POST /games/{id}/load-prebuilt-deck` and the derived `load_prebuilt_deck` MCP tool, and SHALL inject it as `player_ui.playerN` on the DragnCards request so that `$PLAYER_N` resolves while the deck loads.

This is required rather than cosmetic: a Marvel Champions hero deck declares its cards against the templated groups `playerNDeck` and `playerNNemesisSet`, and DragnCards substitutes the `N` from `$PLAYER_N`. A load performed with the wrong seat therefore places that hero's cards into another seat's groups.

The seat SHALL default to `player1` when the caller does not supply one, so that every single-player caller that existed before this capability behaves exactly as it did. A seat that is not one of `player1`, `player2`, `player3` or `player4` SHALL be rejected as a bad request.

#### Scenario: Load a hero deck into the second seat
- **WHEN** a client loads a prebuilt hero deck supplying `player2` as the seat
- **THEN** the Game Service SHALL push the load with `player_ui.playerN` set to `player2`
- **AND** the deck's cards SHALL come to rest in that seat's groups rather than the first seat's

#### Scenario: Loading without a seat still loads into the first seat
- **WHEN** a client loads a prebuilt deck without supplying a seat
- **THEN** the Game Service SHALL push the load as `player1`, unchanged from the behaviour before the seat was accepted

#### Scenario: An unknown seat is refused
- **WHEN** a client loads a prebuilt deck supplying a seat that is not one of the four player seats
- **THEN** the Game Service SHALL reject the request as a bad request and SHALL NOT push any load to DragnCards

### Requirement: Occupied seats match the room's player count
When the Game Service sets a room's player count to N, it SHALL claim each of the seats `player1` through `playerN` that is unoccupied, seating its own DragnCards identity, so that the room's seat map holds an entry for every seat in play.

An entry is required for correct game logging and not merely for display. The Marvel Champions end-of-player-phase automation logs each seat's draw using that seat's recorded alias and suppresses the line entirely when the alias is absent, so an unclaimed seat's draws are missing from the game log that the history and evaluation pipelines read.

A seat already held by a different user SHALL be left alone, because that user is a participant the service did not put there. Claiming SHALL be best-effort: a seat that cannot be claimed SHALL be logged and SHALL NOT fail the player-count change, because a missing log alias must never prevent a game from being set up.

#### Scenario: Raising the player count claims the new seat
- **WHEN** a client sets the player count of a room whose only occupied seat is the first one to two players
- **THEN** the Game Service SHALL claim the second seat for its own identity
- **AND** the room's seat map SHALL afterwards hold an entry for both seats

#### Scenario: A seat held by another user is not taken
- **WHEN** the player count is set and one of the seats within that count is held by a user other than the Game Service's own identity
- **THEN** the Game Service SHALL leave that seat as it is and SHALL claim only the remaining vacant seats

#### Scenario: A failed claim does not fail the player count change
- **WHEN** a seat cannot be claimed while the player count is being set
- **THEN** the Game Service SHALL record the failure and SHALL still report the player-count change as successful with the updated game state

## MODIFIED Requirements

### Requirement: Seat assignment
The Game Service SHALL support assigning a user to a player seat in a game room via the DragnCards `set_seat` channel event, identifying the seat the way DragnCards identifies it.

A seat SHALL be named by its DragnCards seat id — `player1`, `player2`, `player3` or `player4` — because upstream uses that value directly as the key of the room's seat map. A numeric index SHALL NOT be accepted, as no numeric value names a seat and one silently writes a map entry that is not a seat at all. A value that is not one of the four seat ids SHALL be rejected as a bad request.

Because the `set_seat` channel event carries no usable acknowledgement, the Game Service SHALL confirm the assignment by reading room state back and observing that the named seat holds the requested user, and SHALL report failure to the caller when the seat does not take within a bounded wait. Reporting success without that confirmation is not permitted, as it makes a dropped or rejected assignment indistinguishable from an applied one.

#### Scenario: Assign the service to a named seat
- **WHEN** a client sends `POST /games/{id}/seat` naming the seat `player2` and a user id
- **THEN** the Game Service SHALL push `set_seat` on the room channel with `{player_i, new_user_id, timestamp}` where `player_i` is `player2`
- **AND** SHALL report success only after observing that seat holding that user in room state

#### Scenario: A seat that never takes is reported as a failure
- **WHEN** a seat assignment is pushed and the named seat does not come to hold the requested user within the bounded wait
- **THEN** the Game Service SHALL report the assignment as failed rather than as successful

#### Scenario: A numeric or unknown seat is refused
- **WHEN** a client sends `POST /games/{id}/seat` with a seat that is not one of the four player seat ids
- **THEN** the Game Service SHALL return HTTP 422 and SHALL NOT push anything to the room channel

#### Scenario: Seat assignment for non-existent session
- **WHEN** a client sends `POST /games/{id}/seat` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404

### Requirement: Set player count
The Game Service SHALL support setting the number of players for a game room, optionally with a plugin-specific layout, and SHALL bring the room's occupied seats into line with the new count as part of the same operation.

#### Scenario: Set player count
- **WHEN** a client sends `POST /games/{id}/player-count` with `{"num_players": 2}`
- **THEN** the Game Service SHALL push a game action to set `/numPlayers` to 2, wait for state update, and return the updated game state

#### Scenario: Set player count with layout
- **WHEN** a client sends `POST /games/{id}/player-count` with `{"num_players": 2, "layout_id": "standard2Player"}`
- **THEN** the Game Service SHALL push game actions to set `/numPlayers` to 2 and set the layout, wait for state update, and return the updated game state

#### Scenario: Setting the count also claims the seats it implies
- **WHEN** a client sets the player count to a number greater than the count of seats the Game Service currently occupies
- **THEN** the Game Service SHALL claim the vacant seats within that count before returning

#### Scenario: Set player count for non-existent session
- **WHEN** a client sends `POST /games/{id}/player-count` with an unknown session ID
- **THEN** the Game Service SHALL return HTTP 404
