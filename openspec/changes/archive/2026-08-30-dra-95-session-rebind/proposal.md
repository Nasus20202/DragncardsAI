## Why

A provider failure can lead an operator or orchestrator to delete the current game and create a replacement. Persistent orchestrator and seat sessions retain the old server-owned `game_id`, so the replacement game's first state or action call is refused as a cross-game access attempt. Recovery currently requires manually creating a completely new agent session and reconfiguring its seats, which makes reset-and-replay unreliable and easy to get wrong.

## What Changes

- Treat a successful `game-service` `create_game` result as an explicit replay boundary for the calling orchestrator session.
- Allow that orchestrator session to replace its prior game binding with the newly created game's id; failed creation and calls that attach or read an existing game remain immutable and guarded.
- Retire persistent seat-agent sessions from the previous game and clear their seat links so the next `prompt_player_agent` call creates fresh game-bound seat sessions with the existing seat configuration.
- Preserve cross-game refusal for ordinary reads, mutations, `attach_game`, and `lookup_session_by_slug` calls.
- Record the lifecycle contract in the agent-orchestrator specification and cover successful, failed, and unauthorized rebinding paths with tests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: successful explicit game creation starts a new replay boundary and rotates persistent seat sessions without weakening ordinary game-session binding.

## Non-goals

- Do not silently switch a session to an existing game identified by `attach_game`, `lookup_session_by_slug`, or any state/action call.
- Do not change provider retry, failure classification, or job persistence semantics.
- Do not delete the orchestrator transcript or historical seat sessions; retired seat sessions remain terminated for auditability.
- Do not add automatic game deletion, game recreation, or a second game-service authorization mechanism.
