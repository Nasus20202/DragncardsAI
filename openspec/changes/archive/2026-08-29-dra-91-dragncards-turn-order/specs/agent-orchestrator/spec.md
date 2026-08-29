# Platform-aware player-turn authority

## ADDED Requirements

### Requirement: Player-turn prompt freshness follows platform turn authority

The agent-orchestrator SHALL keep the shared normalized player-turn checkpoint platform-aware. The checkpoint SHALL require the common board fields needed to act, but SHALL treat `activeSeat`, `firstPlayer`, and `pendingSeats` as optional on DragnCards: a confirmed `phase=player` is sufficient for the coordinator to continue its configured sequential seat schedule. For marvel-lcg, the checkpoint SHALL require authoritative `pendingSeats` to name the assigned seat in addition to the common fields and SHALL preserve the one-fresh-read-then-stop rule when that engine-owned authority is absent or contradictory.

#### Scenario: A DragnCards seat receives a usable checkpoint without turn metadata

- **WHEN** a DragnCards player prompt carries a complete normalized state with `phase=player` but no `activeSeat`, `firstPlayer`, or `pendingSeats`
- **THEN** the prompt contract SHALL treat the checkpoint as usable
- **AND** the seat SHALL use the current state for its own action rather than stop solely because turn metadata is absent

#### Scenario: A marvel-lcg seat cannot act without matching pending authority

- **WHEN** a marvel-lcg player prompt carries a state with `phase=player` but no `pendingSeats` entry for the assigned seat
- **THEN** the coordinator or seat SHALL perform one fresh authoritative state read
- **AND** it SHALL stop without a move if the fresh state still does not identify the assigned seat
