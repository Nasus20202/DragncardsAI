## Why

An agent session records the game-service game it is playing in `metadata.game_id`, but the MCP dispatch path currently forwards any caller-supplied `session_id`. A player agent can therefore read or mutate another game whenever the downstream service does not independently reject the identifier. Concurrent jobs and reusable player sessions make a one-time binding race possible unless the orchestrator serializes prompt execution and checks parent/child bindings. The orchestrator must enforce its own binding before dispatch so the security boundary does not depend on downstream behavior.

## What Changes

- Add a pure game-session binding guard for game-service tool calls.
- Reject a supplied `session_id` that differs from the current agent session's stored `metadata.game_id` before any game-service request or turn/state preflight is performed.
- Keep first-call discovery for an unbound session, allowing the existing result/argument capture path to bind the first successful game call.
- Serialize prompt jobs per agent session with a Valkey lease before the binding read, dispatch, and capture sequence.
- Preserve server-owned game, platform, restored-context, seat, persona, and orchestrator metadata across ordinary session updates.
- Require an orchestrated player agent to inherit a bound parent game and reject divergent reusable child sessions.
- Return a non-leaking local tool error for rejected calls while preserving a replayable tool-call/tool-result transcript pair.
- Add focused dispatch regression coverage for same-game success, cross-game rejection without target-state leakage, unbound-session first-call binding, concurrent serialization, and parent/child binding.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: bind game-service tool dispatch to the current session's captured game identifier while preserving first-call discovery.

## Non-goals

- Changing game-service seat ownership, turn, or phase enforcement.
- Implementing or changing DRA-62 turn/phase authority checks.
- Implementing or changing DRA-67 seat identity or seat ownership checks.
- Adding authentication or changing the public game-service API.
- Changing lifecycle discovery behavior for an unbound session.
