## 1. Authoritative orchestration guidance

- [x] 1.1 Update `skills/marvel-champions-orchestrator/SKILL.md` so checkpointed state, one-read reconciliation, and abort reporting govern player prompts and round summaries.
- [x] 1.2 Update `skills/marvel-champions-orchestrator/references/player-turn-prompt.md` so normal prompts use verified facts and recovery-only prompts carry a specific finding identifier.
- [x] 1.3 Update `skills/marvel-champions-orchestrator/references/round-loop.md` so encounter cards are tracked, resolved, and checkpointed before the villain phase advances.

## 2. Player recovery guidance

- [x] 2.1 Update `skills/marvel-champions-play/SKILL.md` with the recovery-only finding flow and the requirement to report, rather than guess through, a prompt/state discrepancy.
- [x] 2.2 Update the relevant player recovery reference with the required report fields for finding identifiers and unreliable board state.

## 3. Validate and complete the specification

- [x] 3.1 Run `openspec validate dra-64-improve-skill` and `./scripts/lint.sh` after the skill changes.
- [x] 3.2 Inspect the changed skill contracts against the DRA-64 delta scenarios and record any limitation of live end-to-end play verification.
- [x] 3.3 Archive the completed change so the `game-orchestration` and `marvel-champions-play-skill` main specs reflect the shipped behavior.
- [x] 3.4 Clarify that recovery-only invocations do not replay or consume a completed seat turn.
