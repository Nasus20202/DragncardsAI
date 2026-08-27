## 1. Coordinator contract

- [x] 1.1 Update the DragnCards round-loop reference to read neutral state after setup, advance one beginning-of-round checkpoint, and require `phase=player` before prompting the first seat; verify with `services/agent-orchestrator/tests/unit/test_skill_platform_neutrality.py::test_dragncards_round_loop_enters_player_phase_before_prompting`.
- [x] 1.2 State the failure behavior when the player phase is not confirmed: report the observed state and do not dispatch a seat; verify through the same coordinator-loop regression test and the reviewed reference text.

## 2. Platform projection contract

- [x] 2.1 Pin DragnCards beginning-of-round `roundNumber=0` as `playRound=1` with `phase=passive`, and player step `1.1` as `phase=player`; verify with `services/game-service/tests/unit/test_platform_seam.py`.

## 3. Verification and delivery

- [x] 3.1 Run lint, unit tests, integration tests, and `openspec validate --all`; record the observed results in the Linear issue and pull request.
- [x] 3.2 Run the live DragnCards phase smoke probe and confirm setup/passive advances to player/playRound1/step1.1; delete the probe games afterward.
- [x] 3.3 Push the implementation and this archived contract through PR #441 for owner review.