## 1. Binding Transition

- [x] 1.1 Update game-id capture so only a successful identified `create_game` result can replace an existing orchestrator binding; verify with focused prompt-run tests.
- [x] 1.2 Retire linked persistent seat sessions and clear their links at the successful replacement transition; verify old rows are terminated and seat configuration values remain intact.

## 2. Replay Coverage

- [x] 2.1 Add regression coverage for successful replacement-game creation followed by a game-service call for the new id.
- [x] 2.2 Add regression coverage proving failed creation, existing-game attachment, and ordinary foreign-game calls preserve the original binding and refusal behavior.
- [x] 2.3 Run the agent-orchestrator unit suite and the repository's required lint, integration, and OpenSpec validation commands; record any environment-limited checks.

## 3. Specification and Delivery

- [x] 3.1 Sync or archive the DRA-95 delta into the main agent-orchestrator specification and verify no OpenSpec placeholders remain.
- [x] 3.2 Squash the implementation into the integration branch, confirm the archived change, and update Linear with verification evidence and out-of-scope behavior.
