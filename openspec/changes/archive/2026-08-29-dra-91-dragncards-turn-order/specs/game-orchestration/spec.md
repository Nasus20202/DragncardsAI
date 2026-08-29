# DragnCards and marvel-lcg turn scheduling

## ADDED Requirements

### Requirement: Platform-specific turn checkpoints preserve each platform's authority

The orchestrator SHALL apply the turn checkpoint appropriate to the bound game platform before prompting a player seat. For a DragnCards session, a normalized state with a usable `playRound`, `phase`, `mode`, `players`, and `zones` and `phase=player` SHALL authorize continuing through the configured seats in sequential player order; absent `activeSeat`, `firstPlayer`, and `pendingSeats` metadata SHALL NOT by itself block that continuation. For a `marvel-lcg` session, the orchestrator SHALL require the normalized `pendingSeats` list to identify the seat being prompted, because the rules engine owns turn scheduling; absence or contradiction of that authority SHALL trigger one fresh state read and then a stop without prompting if unresolved.

#### Scenario: DragnCards continues a confirmed player phase without turn metadata

- **WHEN** a DragnCards normalized state has `phase=player` and usable `playRound`, `mode`, `players`, and `zones`, but omits `activeSeat`, `firstPlayer`, and `pendingSeats`
- **THEN** the orchestrator SHALL continue the current player phase using the configured seats in sequential order
- **AND** it SHALL prompt the next configured seat only after the prior seat's report is received

#### Scenario: DragnCards still blocks an unconfirmed phase

- **WHEN** a DragnCards normalized state omits the turn metadata and its phase is `setup`, `passive`, `villain`, or `unknown`
- **THEN** the orchestrator SHALL NOT prompt a player seat
- **AND** it SHALL follow the existing platform transition or report the unresolved state

#### Scenario: marvel-lcg missing pending-seat authority blocks prompting

- **WHEN** a marvel-lcg normalized state is otherwise usable and reports `phase=player` but omits `pendingSeats` or does not name the configured seat
- **THEN** the orchestrator SHALL perform one fresh authoritative state read
- **AND** it SHALL stop without prompting that seat if the fresh state still lacks a matching pending seat

#### Scenario: marvel-lcg pending-seat authority remains stronger than phase

- **WHEN** a marvel-lcg normalized state names a configured seat in `pendingSeats`, even if its broad phase label is setup, passive, or otherwise non-player
- **THEN** the orchestrator SHALL treat that pending seat as the engine-authorized decision owner
- **AND** it SHALL not replace the engine's pending-seat decision with configured sequential scheduling
