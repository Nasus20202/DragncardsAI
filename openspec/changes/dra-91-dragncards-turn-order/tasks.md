## 1. Platform-specific coordinator contract

- [x] 1.1 Update the orchestrator skill and DragnCards round-loop reference so a confirmed DragnCards `phase=player` continues through configured sequential seats when `activeSeat`, `firstPlayer`, and `pendingSeats` are absent, while non-player phases still stop or transition; verify with the focused skill-contract test.
- [x] 1.2 Update the shared player-turn prompt reference so optional DragnCards turn metadata is not treated as a required checkpoint, while marvel-lcg still requires a matching authoritative `pendingSeats` entry and one fresh read before stopping; verify with focused platform-contract assertions.

## 2. Runtime prompt and regression proof

- [x] 2.1 Render the persistent player-session memory contract according to the bound platform, allowing DragnCards continuation from a confirmed player phase and retaining marvel-lcg pending-seat blocking; verify generated prompts for both platforms.
- [x] 2.2 Add focused unit coverage for DragnCards missing-seat metadata continuation and marvel-lcg missing-seat blocking, then run only the affected orchestrator unit tests and OpenSpec validation.
- [x] 2.3 Mark all implementation tasks complete after the focused checks pass and commit the coherent DRA-91 change on the feature branch.
