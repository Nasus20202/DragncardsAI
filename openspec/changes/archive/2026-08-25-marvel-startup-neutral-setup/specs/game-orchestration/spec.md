## ADDED Requirements

### Requirement: Orchestrated setup uses discovered typed selections

The orchestrator skill SHALL require setup discovery through `list_game_setup_catalog` before
creating a game. It SHALL select a scenario id and an ordered list of each configured neutral seat
and its requested hero-deck id, then pass those values in the outer `setup` field of the typed
`create_game` specification. The roster SHALL be the contiguous `player1`..`playerN` prefix. It
SHALL not hardcode a Marvel hero, choose the first catalog entry, infer a deck
from a prompt after creation, or enter the round loop until the returned setup metadata and state
confirm every seat's requested hero.

#### Scenario: A prompted roster controls the created heroes

- **WHEN** an orchestrator has a roster requesting hero deck `H1` for `player1` and `H2` for
  `player2`
- **THEN** it SHALL discover those ids, create the game with the ordered typed setup, and verify
  that the resulting state assigns `H1` and `H2` to the corresponding seats
- **AND** it SHALL not substitute a fixed or first-listed hero

#### Scenario: Setup cannot be inferred after creation

- **WHEN** the returned setup metadata or state does not confirm a configured seat's requested
  hero
- **THEN** the orchestrator SHALL stop and report the mismatch
- **AND** it SHALL not enter the round loop or silently continue with the wrong hero

#### Scenario: Missing setup data stops the orchestrator

- **WHEN** a configured seat has no valid hero-deck id or the catalog does not contain a requested
  scenario/deck
- **THEN** the orchestrator SHALL report the missing or invalid selection
- **AND** it SHALL not create a game using a catalog default

### Requirement: The orchestrator selects moves from declared platform capabilities

The orchestrator SHALL read `platform` and `move_surface` from the created session metadata and
shall use only the surface declared for that session. It SHALL retain DragnCards typed-action
setup and phase tools, and shall use Marvel's enumerated option tools with their `player_n`
argument and required prompt identity when the session declares `move_surface: enumerated_options`.

#### Scenario: Marvel setup does not call DragnCards actions

- **WHEN** a created session declares `platform: marvel-lcg` and
  `move_surface: enumerated_options`
- **THEN** the orchestrator SHALL not issue DragnCards typed setup or raw DragnLang actions
- **AND** it SHALL use the neutral state and enumerated option contract instead

#### Scenario: Capability metadata is authoritative for dispatch

- **WHEN** a session's available tool list is incomplete or cached
- **THEN** the orchestrator SHALL use the session metadata and server-side refusal as authority
- **AND** it SHALL not infer that one backend can accept the other backend's move surface
