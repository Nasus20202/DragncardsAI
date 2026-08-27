## Context

The history UI already receives the agent move payload and the evaluator already receives an optional player target. The missing behavior is at the presentation and context-window boundaries: the UI discards the move's player value from its summary, while neighbouring-move selection ignores the target player.

## Goals / Non-Goals

**Goals:**

- Make multiplayer agent moves distinguishable without changing the history event schema.
- Prevent attributed move-scoped judge prompts from including another seat's move context.
- Preserve the existing aggregate behavior for unattributed legacy chat moves.

**Non-Goals:**

- Changing history persistence, event attribution, round boundaries, or evaluation fan-out.
- Filtering round- or game-scoped roll-up inputs to one seat.
- Changing the upstream DragnCards protocol.

## Decisions

- **Render the existing player id as a compact summary label.** A new server field would duplicate data already persisted and would require a contract migration. Deriving the label from the event payload keeps the UI compatible with current and legacy history responses.
- **Filter neighbouring moves at the shared selection boundary.** Filtering only in the prompt builder would leave other consumers with the same cross-seat leakage. Adding an optional player constraint to neighbouring selection keeps all move-input callers consistent; `None` preserves existing aggregate behavior.
- **Use the target event's player when the caller does not supply one.** Round assembly passes an explicit player for per-player roll-ups, while move assembly must still protect a target whose own recorded payload carries its seat. Trusting an explicit target player argument preserves the evaluator's per-player attribution.
- **Keep roll-up context unchanged.** Filtering round/game inputs would remove legitimate board-changing actions by other cooperative players and alter the established grading contract. Only the move-scoped private decision context requires isolation.

## Risks / Trade-offs

- Player ids are platform/application data and may be unfamiliar strings; rendering them verbatim is more accurate than inventing display names, and the label is plain text.
- The upstream DragnCards WebSocket does not participate in this change. If it omits or changes the producer's player attribution, legacy omission behavior remains safe but the UI cannot identify that move until the producer supplies the value.
- Some older events have no player field. They retain aggregate context and no label, avoiding a fabricated attribution while preserving historical readability.
