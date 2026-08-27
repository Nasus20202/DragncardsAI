## Context

See `proposal.md` for the motivation. The DragnCards normalizer already converts `roundNumber=0` to neutral `playRound=1` and classifies step `0.0` as `passive` and step `1.1` as `player`. The coordinator reference previously moved from setup directly to the first seat without making that transition explicit.

## Goals / Non-Goals

**Goals:**

- Make the beginning-of-round checkpoint explicit in the DragnCards coordinator loop.
- Ensure the first seat is prompted only after a fresh state read confirms the player phase.
- Pin the platform vocabulary and neutral round behavior with regression tests.

**Non-Goals:**

- Adding server-side turn authority to the DragnCards platform.
- Changing the normalizer's conversion rules or the player agent's available tools.
- Altering the villain phase or the rules-enforcing marvel-lcg loop.

## Decisions

### Decision 1: Use the neutral state as the transition checkpoint

The coordinator will read `playRound`, `stepId`, `phase`, and `phaseLabel` after setup and again after the transition. It will use the normalized `phase` to decide whether a seat can be prompted, while retaining `stepId` and `phaseLabel` for diagnosing a failed transition.

**Alternative rejected: use only the raw step id.** Raw step ids are DragnCards vocabulary and do not provide the backend-neutral contract used by the rest of the orchestration loop.

**Alternative rejected: infer the transition from the returned action response.** A successful transport response does not prove that the WebSocket state changed; a fresh state read is the only observable confirmation.

### Decision 2: Advance exactly once from the beginning-of-round checkpoint

When the state is DragnCards step `0.0` with neutral phase `passive`, the coordinator will call `next_step` once, then re-read state. It will not prompt a seat while the board remains passive.

**Alternative rejected: prompt the first seat immediately.** That sends a player action into setup/passive state and causes the seat to be blamed for a round-loop transition it does not own.

**Alternative rejected: repeatedly call `next_step` until a player phase appears.** Repeated advancement could skip a platform state or apply an unintended action; one deliberate call followed by confirmation keeps the protocol interaction bounded.

### Decision 3: Stop on an unconfirmed player phase

If the post-transition read does not report `phase=player`, the coordinator will report the observed state and stop seat dispatch for that round. It will not infer success, ask a player to undo a move, or apply a second round-number correction.

**Alternative rejected: continue optimistically.** Continuing would recreate the original misattribution and could mutate the board from an invalid phase.

### Decision 4: Test both the platform projection and coordinator contract

Regression tests will assert the DragnCards normalizer's beginning-of-round and player-phase projections, and will assert ordering in the coordinator reference: state read, transition call, confirmation, then first-seat prompt.

**Alternative rejected: test only the markdown reference.** That would not protect the state projection consumed by the coordinator.

**Alternative rejected: test only the normalizer.** A correct projection does not prove that the coordinator waits for it before dispatching a seat.

## Risks / Trade-offs

- DragnCards WebSocket state is asynchronous and owned by an upstream service. The explicit post-action read may add one round trip, but it prevents treating an acknowledged request as proof that the phase changed.
- The coordinator reference names DragnCards step ids because this transition is platform-specific. Those ids remain confined to the DragnCards reference; the neutral `phase` and `playRound` fields remain the cross-platform contract.
- If upstream changes the beginning-of-round step or label, the checkpoint will stop and report the observed state rather than silently prompt a seat. The regression fixture makes such drift visible.