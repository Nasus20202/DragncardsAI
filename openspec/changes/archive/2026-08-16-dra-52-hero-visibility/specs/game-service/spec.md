## ADDED Requirements

### Requirement: A prebuilt deck load covers the seat's layout before loading

When the Game Service loads a prebuilt deck for a seat beyond the room's current
player count, it SHALL first raise the player count — and with it the table layout —
to cover that seat, and only then push the deck load. The layout SHALL be the one
the plugin's `playerCountMenu` maps the new count to (e.g. Marvel Champions maps
`2` to `standard2Player`), and the bump SHALL NOT apply when the seat is `player1`
or is already covered by the current count.

This exists because DragnCards renders only the groups that have a region in the
room's active layout. A hero deck loaded for `player2` while the room is still laid
out for one player puts that hero's cards into groups with no region: they exist in
the game state (so MCP state reads show them) but never appear on the table, and
setting the player count afterwards is what makes them appear. The human setup flow
sets the count first; this guard replicates that order for automated callers that
get it wrong (DRA-52).

The guard SHALL live in the prebuilt-deck load path shared by
`POST /games/{id}/load-prebuilt-deck` and the derived `load_prebuilt_deck` MCP tool,
so every caller is covered regardless of call order.

#### Scenario: Loading a second hero deck before the player count is set

- **WHEN** a client loads a prebuilt hero deck for `player2` while the room's player
  count is still 1
- **THEN** the Game Service SHALL raise the player count to 2 and switch the layout
  to the plugin's two-player layout before pushing the load
- **AND** the deck's cards SHALL come to rest in `player2`'s groups
- **AND** the room's state SHALL afterwards report `numPlayers: 2` and the
  two-player layout id

#### Scenario: A seat the count already covers is not bumped

- **WHEN** a client loads a prebuilt deck for a seat at or below the room's current
  player count
- **THEN** the Game Service SHALL push the load without changing the player count or
  layout

#### Scenario: The first seat is never bumped

- **WHEN** a client loads a prebuilt deck for `player1` with no player count set
- **THEN** the Game Service SHALL push the load and SHALL leave the player count and
  layout unchanged
