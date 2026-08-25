# Marvel setup integrity and render progress

## Purpose

The Marvel LCG driver must prove that the singleton engine is running the setup selected
by the caller and must drive the engine's render acknowledgement protocol without hanging.

## ADDED Requirements

### Requirement: Selected setup is verified before session readiness

The game-service Marvel driver SHALL retain the selected scenario and ordered hero-deck
identities from the fetched catalog documents. Before a newly created session is returned,
it SHALL obtain a ready engine world and verify the selected player count and one matching
hero identity per ordered seat, plus a matching selected scenario villain and main scheme
from the visible world areas or their corresponding decks.

#### Scenario: Selected Rhino setup is returned only after matching validation

- **WHEN** a caller selects a Rhino scenario and an ordered hero-deck list
- **THEN** the driver SHALL return a session only after the first ready world contains the
  selected player identities and Rhino scenario witnesses

#### Scenario: A default or mismatched board is rejected

- **WHEN** the engine returns a world whose player identity, player count, villain, or main
  scheme does not match the selected setup
- **THEN** session creation SHALL fail with a descriptive setup-integrity error
- **AND** SHALL NOT return a session claiming the selected setup

#### Scenario: A malformed ready world is rejected

- **WHEN** the first ready world cannot supply a required selected-setup witness
- **THEN** the driver SHALL fail clearly rather than substitute a catalog entry or accept
  the world as ready

### Requirement: Render acknowledgement is load-bearing and bounded

The Marvel driver SHALL acknowledge each processed non-degraded render frame for its seat
using the frame's render and game identifiers. Acknowledgement failures SHALL retry only a
bounded configured number of times. After exhaustion the driver SHALL mark that seat's
transport degraded, notify the state-unavailable handler, and fail the operation that
requires acknowledged progress with a transport error.

#### Scenario: Empty pending reveal advances after acknowledgement

- **WHEN** the engine sends a frame with `ask_players=[]` while a reveal or setup step is
  in progress
- **THEN** the driver SHALL acknowledge and consume that frame
- **AND** SHALL continue waiting for a later frame that names a held seat
- **AND** SHALL NOT invent or submit an option for the empty pending-seat list

#### Scenario: Acknowledgement failure degrades explicitly

- **WHEN** the engine does not accept a frame acknowledgement within the configured retry
  budget
- **THEN** the driver SHALL stop waiting or submitting for that seat
- **AND** SHALL report render transport degradation instead of hanging indefinitely

#### Scenario: Empty options remain empty

- **WHEN** the engine reports no pending ask for a seat
- **THEN** the driver SHALL return an empty option projection
- **AND** SHALL reject a choice because the seat has no pending decision

### Requirement: Startup fallback cannot replace a requested game

The repository-owned Marvel engine image SHALL disable the upstream fallback that silently
loads the hardcoded Rhino and Spider-Man scene when a configured startup save cannot be
loaded. The image build SHALL apply this hardening as an exact zero-fuzz patch, and a
startup-save failure SHALL remain an explicit engine failure.

#### Scenario: A missing configured startup save fails closed

- **WHEN** the engine is configured to load a startup save and that save is absent or invalid
- **THEN** the engine SHALL fail explicitly
- **AND** SHALL NOT create the hardcoded Rhino versus Spider-Man fallback scene
