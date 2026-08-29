## Context

The orchestrator is an LLM-guided round loop whose platform-specific authority is expressed in the shipped orchestrator skill and injected player-session prompt. The current generic freshness wording is stronger than the platform contracts: it can make a DragnCards coordinator treat absent optional turn markers as a failed checkpoint, even though DragnCards exposes a composing playtable and the coordinator owns configured seat order. The runtime turn guard already treats a platform without pending prompts as phase-only; this change aligns the coordinator and seat-facing instructions with that existing distinction.

## Goals / Non-Goals

**Goals:**

- Make all coordinator and persistent-seat guidance agree that DragnCards `phase=player` permits configured sequential scheduling without `activeSeat`, `firstPlayer`, or `pendingSeats`.
- Keep the marvel-lcg checkpoint engine-authoritative: a matching `pendingSeats` entry is required before a seat is prompted, with one fresh read and stop on unresolved absence or contradiction.
- Pin both paths with deterministic, focused tests that inspect the actual skill and generated persistent-seat prompt surfaces.

**Non-Goals:**

- No changes to game-service normalized state, DragnCards WebSocket handling, Marvel LCG engine behavior, or turn-sensitive tool sets.
- No changes to provider metadata, model catalogs, dashboard selection, card ownership, terminal-state logic, or phase automation.

## Decisions

### Use platform-specific wording at every prompt boundary

The coordinator skill, DragnCards round-loop reference, and shared player-turn reference will describe the common normalized fields separately from platform-owned turn authority. The DragnCards path will explicitly say that a confirmed player phase is enough and that configured seats are prompted sequentially. The marvel-lcg path will retain the pending-seat requirement and bounded refresh behavior.

**Alternatives considered:**

- **Change only the DragnCards round-loop reference:** rejected because the top-level skill and shared player prompt would still tell a coordinator or seat to stop on missing authority.
- **Remove all missing/contradictory checkpoint checks:** rejected because malformed board state and Marvel LCG's engine-owned pending decision still require a bounded stop.

### Keep the runtime seat memory contract platform-aware

`build_subagent_system_prompt` already receives the bound platform. The persistent-seat memory contract will be rendered with a platform-specific authority paragraph so a DragnCards seat does not inherit the old blanket stop rule, while a marvel-lcg seat still receives the strict pending-seat rule. The common stale-history and terminal-state rules remain shared.

**Alternatives considered:**

- **Rely only on injected skill markdown:** rejected because the runtime contract is deliberately placed before persona text and is a direct enforcement boundary for persistent seats.
- **Add a new runtime scheduler or state parser:** rejected because seat scheduling is coordinator-owned prompt behavior, and game-service already supplies the normalized state; a second parser would duplicate authority and risk platform drift.

### Test observable contracts, not implementation text alone

Focused unit tests will assert the DragnCards loop/reference and generated DragnCards seat prompt explicitly allow missing turn metadata, and assert the Marvel LCG loop/reference and generated Marvel LCG seat prompt retain pending-seat blocking. Existing tests for phase transitions, pending-seat authority, and stale history remain unchanged.

**Alternatives considered:**

- **Exercise a live game stack:** rejected for this regression because the missing metadata is a deterministic normalized-state contract and the prompt scheduler is model-driven; static contract tests provide repeatable proof without network or upstream state.

## Risks / Trade-offs

- DragnCards configured order may not match a hidden first-player marker. This is intentional platform behavior: DragnCards does not expose that marker in the normalized projection, and its configured sequential order is the coordinator's declared authority. The phase automation remains unchanged.
- A future DragnCards normalizer could add turn metadata. The instructions will continue to permit using it when present, but absence will remain non-blocking so older and newer projections behave consistently.
- A careless shared-contract edit could weaken Marvel LCG. The tests will check both generated platform prompts and the explicit marvel-lcg reference for the required pending-seat stop.
