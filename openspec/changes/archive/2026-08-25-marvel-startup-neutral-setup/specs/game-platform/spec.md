## ADDED Requirements

### Requirement: Platform creation uses a typed platform-owned specification

The `GamePlatform` protocol SHALL accept a typed, platform-discriminated create specification
rather than an untyped mapping named `plugin_info`. The specification SHALL have exactly one
variant for each supported platform. The DragnCards variant SHALL carry its plugin selection; the
marvel-lcg variant SHALL carry a `scenario_id` and an ordered non-empty contiguous prefix of
neutral `player1`..`playerN` seat and `hero_deck_id` pairs.

The API boundary SHALL validate the discriminator, required fields, neutral seat vocabulary,
contiguous roster order, duplicate seats, and catalog membership before invoking a driver. A driver SHALL not silently
discard fields belonging to another platform, infer a platform from plugin metadata, or replace an
invalid requested identifier with another catalog entry.

#### Scenario: A Marvel create spec reaches the Marvel driver typed

- **WHEN** a caller creates a marvel-lcg game with a scenario id and ordered seat/deck pairs from
  the setup catalog
- **THEN** game-service SHALL pass a marvel-lcg create-spec object to the Marvel driver
- **AND** the driver SHALL preserve the pair order when resolving hero documents
- **AND** no `plugin_info` mapping SHALL be used as the cross-platform contract

#### Scenario: A setup discriminator cannot select another platform

- **WHEN** a create request names `platform: marvel-lcg` but supplies a DragnCards create spec
- **THEN** the request SHALL be refused before either backend is called
- **AND** the error SHALL identify the mismatched platform discriminator

#### Scenario: Duplicate or unknown setup selections are rejected

- **WHEN** a create request repeats a seat, uses a seat outside `player1` through `player4`, or
  names a scenario/deck id absent from the selected platform catalog
- **THEN** the request SHALL be refused before table creation
- **AND** no different catalog entry SHALL be substituted

### Requirement: Platform capability metadata is explicit

Each platform driver SHALL declare a stable `platform` slug and exactly one `move_surface` slug.
The supported move surfaces SHALL be `typed_actions` for DragnCards and `enumerated_options` for
marvel-lcg. The capability declaration SHALL be available without creating a game and SHALL be
carried on every session metadata response and session action catalog.

#### Scenario: DragnCards declares its typed surface

- **WHEN** a caller reads the DragnCards platform capability
- **THEN** the response SHALL contain `platform: dragncards` and
  `move_surface: typed_actions`

#### Scenario: Marvel declares its enumerated surface

- **WHEN** a caller reads the marvel-lcg platform capability
- **THEN** the response SHALL contain `platform: marvel-lcg` and
  `move_surface: enumerated_options`

#### Scenario: Capability metadata does not imply cross-surface translation

- **WHEN** a caller uses a move operation not offered by the session's declared move surface
- **THEN** the driver SHALL refuse it with the platform and offered surface
- **AND** SHALL not translate or partially execute the request

### Requirement: Singleton platforms expose ownership constraints

A platform driver whose engine supports one active game SHALL declare that ownership constraint to
the session manager. The manager SHALL acquire and renew one distributed lease per engine endpoint
before creating or mutating a session, and SHALL release it during teardown. A lost lease SHALL
fence subsequent mutating operations and mark the session degraded.

#### Scenario: A second Marvel session cannot claim the engine

- **WHEN** a second session requests a Marvel table while the endpoint lease belongs to another
  active session
- **THEN** creation SHALL be rejected with a conflict naming the singleton constraint
- **AND** the second session SHALL not send a create request to the engine

#### Scenario: Lease loss prevents unowned mutation

- **WHEN** a Marvel session cannot renew its endpoint lease
- **THEN** the session SHALL become degraded
- **AND** subsequent moves SHALL be refused until a new owned session is created

#### Scenario: Unsupported singleton attachment is explicit

- **WHEN** a caller attempts to attach a Marvel session using a service-generated slug
- **THEN** the driver SHALL refuse the attachment as unsupported
- **AND** SHALL not attach to whichever singleton game happens to be active
