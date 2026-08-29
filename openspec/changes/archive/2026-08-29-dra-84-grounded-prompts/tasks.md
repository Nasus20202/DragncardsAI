## 1. Grounded prompt contract

- [x] 1.1 Replace the old fixed DragnCards player prompt with one platform-neutral envelope containing the latest normalized state checkpoint and exact current engine prompt where available.
- [x] 1.2 Document normalized-state authority, sparse omitted fields, opaque phase labels, main/side scheme locations, one-refresh-then-stop contradiction handling, and no-coaching prompt construction.
- [x] 1.3 Update the orchestrator skill, reality notes, and both platform round-loop references to discover and require the sole player-turn prompt contract.

## 2. Persistent seat runtime boundary

- [x] 2.1 Add an immutable player-session memory contract to the seat subagent system prompt that invalidates replayed facts between invocations and allows one fresh authoritative state read before stopping.
- [x] 2.2 Wire the contract only to sessions identified as player seats and update the `prompt_player_agent` tool description so the runtime catalogue carries the same authority requirements.
- [x] 2.3 Gate terminal claims on normalized `mode` or an explicitly terminal engine response, including the remaining-HP Rhino regression.

## 3. Focused proof

- [x] 3.1 Add deterministic tests for contract discoverability, forbidden coordinator coaching, the Rhino `9/14` → `12/14` → `14/14` sequence with villain HP remaining, and stale persistent-fact invalidation.
- [x] 3.2 Run the focused orchestrator prompt-contract tests and OpenSpec validation; record exact commands and results in the implementation report.
