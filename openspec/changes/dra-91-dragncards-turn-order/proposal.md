## Why

The platform-neutral player-turn contract currently treats missing turn metadata as an unresolved checkpoint even when a DragnCards state has already confirmed the player phase. DragnCards does not expose an authoritative active seat, first-player marker, or pending-seat list in its normalized projection, so this incorrectly stops a valid orchestrated round instead of letting the coordinator continue through its configured seat order.

## What Changes

- Make the DragnCards orchestration checkpoint require a usable normalized state and confirmed `phase: player`, but not optional active-seat, first-player, or pending-seat metadata.
- State that a DragnCards player phase uses the coordinator's configured sequential seat order when those optional turn fields are absent, while retaining first-player automation where the platform exposes it.
- Keep marvel-lcg's stricter engine-owned turn contract: a seat may be prompted only when authoritative `pendingSeats` identifies it, and a missing or contradictory pending-seat checkpoint gets one fresh read followed by a stop.
- Add focused regression tests that prove DragnCards continuation and marvel-lcg blocking remain distinct.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `game-orchestration`: distinguish DragnCards coordinator-owned sequential seat scheduling from marvel-lcg's authoritative pending-seat scheduling when normalized turn metadata is absent.
- `agent-orchestrator`: make the shared player-turn checkpoint and persistent-seat guidance platform-aware for missing turn metadata.

## Non-goals

- Do not change provider reasoning, model catalogs, or dashboard selection.
- Do not change game-service normalization or invent active-seat metadata.
- Do not weaken marvel-lcg engine turn validation or pending-seat requirements.
- Do not alter card ownership, phase transitions, villain automation, terminal-state rules, or move semantics.
