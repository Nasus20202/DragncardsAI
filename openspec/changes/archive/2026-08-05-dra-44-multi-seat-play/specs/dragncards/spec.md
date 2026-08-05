## ADDED Requirements

### Requirement: A seat is a slot in a room, not an authenticated identity
The integration contract with DragnCards SHALL record that a room's seats are the keys `player1` through `player4` of one seat map held in that room's server process, and that the seat an action acts as is taken from the action's own payload rather than from the identity of the connection that sent it.

The acting seat SHALL be understood to come from `options.player_ui.playerN` on the `game_action` event, which the backend grafts onto the game state and from which the `$PLAYER_N` variable — the value all player-scoped plugin automation branches on — resolves. The authenticated user carried by the websocket SHALL be understood to select the user's language, attribute a saved replay, and route a targeted GUI update, and SHALL NOT be understood to authorize, restrict, or determine the seat an action acts as.

The consequence the Game Service depends on SHALL be stated plainly: one authenticated connection can act as every seat of a room, and a multi-player game therefore requires no additional DragnCards account.

#### Scenario: One connection acts as two seats
- **WHEN** the Game Service, connected as a single authenticated user, pushes one action naming `player1` and another naming `player2`
- **THEN** the DragnCards backend SHALL apply each action to the named seat's cards and groups, regardless of which seat that user occupies

#### Scenario: An action that needs a seat and omits it fails
- **WHEN** the Game Service pushes an action whose DragnLang references `$PLAYER_N` and whose payload carries no `player_ui.playerN`
- **THEN** the DragnCards backend SHALL fail that action with `Variable $PLAYER_N is undefined` rather than choosing a seat on the caller's behalf

### Requirement: Seat occupancy governs how a seat is named in the game log
The integration contract SHALL record that the room's seat map supplies the alias by which a seat is named in the game log, and that a seat with no entry in that map is not merely unnamed but can be omitted from the log entirely.

Plugin automation reads a seat's alias out of the seat map and, where it guards a log line on that alias being defined, writes no line at all when the seat is unoccupied. Because the game log is what the history and evaluation pipelines consume, an unoccupied seat's actions can therefore be absent from the recorded game rather than merely anonymous.

#### Scenario: An occupied seat is named in the log
- **WHEN** an action logs on behalf of a seat that holds a user in the room's seat map
- **THEN** the log line SHALL name that user's alias

#### Scenario: An unoccupied seat can be omitted from the log
- **WHEN** the end-of-player-phase automation runs for a seat with no entry in the room's seat map
- **THEN** that seat's draw SHALL NOT appear in the game log, while an occupied seat's draw SHALL appear

### Requirement: Seat assignment is addressed by seat id
The DragnCards backend SHALL accept seat assignment on the room channel as a `set_seat` event whose `player_i` is a seat id — `player1` through `player4` — because that value is used directly as the key of the room's seat map.

The Game Service SHALL NOT send a numeric index for this field, as no numeric value names a seat and sending one writes an entry into the seat map that no seat lookup will ever find.

Because the backend's handling of this event returns no acknowledgement that distinguishes an applied assignment from a rejected one, the Game Service SHALL treat the room's subsequent state as the authority on whether a seat was taken.

#### Scenario: Assign a seat by its seat id
- **WHEN** the Game Service pushes `set_seat` with `player_i` set to `player2` and a user id
- **THEN** the DragnCards backend SHALL record that user in the second seat of the room's seat map

#### Scenario: Occupancy is confirmed from state, not from the push
- **WHEN** the Game Service needs to know whether a seat assignment took effect
- **THEN** it SHALL read the room's state and inspect the seat map, rather than inferring success from having sent the event
