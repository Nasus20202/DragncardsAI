# DragnCards Integration Contract

## ADDED Requirements

### Requirement: This contract describes one platform, not every platform

This capability SHALL be read as the integration contract for the DragnCards platform specifically:
what the DragnCards backend provides, and how the Game Service's DragnCards driver MUST use it. It
SHALL NOT be read as the contract every game platform satisfies, and a requirement stated here SHALL
NOT be taken to constrain another platform.

The cross-platform contract SHALL live in the `game-platform` capability, and every operation named
here SHALL be understood as the DragnCards driver's implementation of one of that protocol's
operations: authenticating, creating a table, attaching to an existing table, connecting, requesting
state, executing a move, assigning a seat, setting spectator visibility, and tearing down.

Consequently, the vocabulary this capability uses — Phoenix Channels, room slugs, room channels,
DragnLang action lists, plugin identity, `set_game`, `set_seat` — SHALL be understood as DragnCards
vocabulary. It SHALL NOT be required of, mapped onto, or fabricated for any other platform, and no
module above the DragnCards driver SHALL depend on it.

#### Scenario: A DragnCards fact is not applied to another platform
- **WHEN** a reader consults this capability for how a platform authenticates, creates a table, or executes a move
- **THEN** the answer SHALL apply only to sessions whose platform is `dragncards`
- **AND** the platform-neutral obligation SHALL be taken from the `game-platform` capability instead

#### Scenario: DragnCards vocabulary stays behind the DragnCards driver
- **WHEN** the Game Service's modules above the platform driver are inspected
- **THEN** none of them SHALL reference a Phoenix event name, a room channel topic, a DragnLang action list, or a plugin identifier
- **AND** every such reference SHALL live in the DragnCards driver or in this capability's own contract

#### Scenario: A second platform is not held to this contract
- **WHEN** a session whose platform is not `dragncards` is created and driven
- **THEN** no requirement of this capability SHALL be asserted against it
- **AND** its own platform capability SHALL be the contract that governs it

## MODIFIED Requirements

### Requirement: Plugin availability
The DragnCards backend SHALL have plugins installed and accessible for use when creating game rooms.

A plugin identity — `plugin_id`, `plugin_version` and `plugin_name` — SHALL be understood as naming a
row in DragnCards' own plugin table and therefore as a DragnCards concept only. It SHALL NOT be used
to identify, infer, or carry the platform a session plays on, because a platform that has no plugin
notion would have to be described by a fabricated plugin identity. The platform SHALL be carried by
its own explicit discriminator, as required by the `game-platform` capability.

#### Scenario: Marvel Champions plugin available
- **WHEN** the DragnCards backend is started with the Marvel Champions plugin volume mounted at `/plugin`
- **THEN** the plugin SHALL be registered and its `plugin_id` and `plugin_version` SHALL be known to the Game Service via environment-injected configuration

#### Scenario: Plugin loaded on room creation
- **WHEN** a room is created with a valid `plugin_id` and `plugin_version`
- **THEN** the DragnCards backend SHALL load the plugin into the room, and the initial `current_state` broadcast SHALL reflect an initialized game

#### Scenario: Plugin identity is not a platform discriminator
- **WHEN** a consumer needs to know which platform produced a session, an event, a snapshot, or an evaluation
- **THEN** it SHALL read the explicit platform discriminator
- **AND** SHALL NOT derive the platform from `plugin_name`, `plugin_id`, or `plugin_version`

### Requirement: Seat occupancy governs how a seat is named in the game log
The DragnCards integration contract SHALL record that a DragnCards room's seat map supplies the alias by which a seat is named in the game log, and that a seat with no entry in that map is not merely unnamed but can be omitted from the log entirely.

DragnCards plugin automation reads a seat's alias out of the seat map and, where it guards a log line on that alias being defined, writes no line at all when the seat is unoccupied. Because the game log is what the history and evaluation pipelines consume, an unoccupied seat's actions can therefore be absent from the recorded game rather than merely anonymous.

This is a property of DragnCards' plugin automation and SHALL NOT be assumed of another platform, whose engine records a seat's actions without reference to any occupancy map.

#### Scenario: An occupied seat is named in the log
- **WHEN** a DragnCards action logs on behalf of a seat that holds a user in the room's seat map
- **THEN** the log line SHALL name that user's alias

#### Scenario: An unoccupied seat can be omitted from the log
- **WHEN** the end-of-player-phase automation runs for a DragnCards seat with no entry in the room's seat map
- **THEN** that seat's draw SHALL NOT appear in the game log, while an occupied seat's draw SHALL appear

#### Scenario: The omission is not assumed of another platform
- **WHEN** a consumer of recorded games reasons about a missing seat's actions
- **THEN** it SHALL apply this omission rule only to games whose platform is `dragncards`
