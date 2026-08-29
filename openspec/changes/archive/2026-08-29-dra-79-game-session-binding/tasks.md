## 1. Implement the dispatch binding

- [x] 1.1 Add a pure game-session binding guard that compares a supplied game-service `session_id` with the current session's stored `metadata.game_id`, while allowing unbound first calls; verify with focused unit coverage for matching, mismatching, unbound, and non-game-service inputs.
- [x] 1.2 Invoke the binding guard at the prompt tool-dispatch boundary before seat/turn preflight and before MCP forwarding; return a local error tool result for mismatches without changing the session binding or exposing a downstream response; verify with same-game and cross-game dispatch tests.
- [x] 1.3 Preserve existing first-call game-id capture for an unbound session and verify the successful call persists its game identifier for subsequent calls.
- [x] 1.4 Keep game binding, platform, restored context, and agent identity metadata immutable across ordinary session metadata updates; verify client replacements are ignored and existing values are preserved.
- [x] 1.5 Serialize prompt jobs per session with a Valkey lease acquired before the binding read, and verify contending tasks execute one at a time.
- [x] 1.6 Require orchestrated player agents to inherit a bound parent game and reject or reconcile child sessions whose binding diverges; verify unbound-parent and cross-game-child cases.

## 2. Record the contract

- [x] 2.1 Complete the DRA-79 OpenSpec proposal, capability delta, design decisions, and checked implementation task list with no placeholders; verify the change status reports all artifacts complete.
