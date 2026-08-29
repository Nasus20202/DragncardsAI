## Context

See `proposal.md` for the user-visible failure. The trace shows the failure boundary is the DragnCards phase action, not normalization: the plugin `drawBoost` action moves the top encounter card to `<player>Engaged`, sets `rotation` to `-30`, and sets `boost` to `true`; the plugin `villainEndPhase` action only changes first player, step, round, and log text. The DragnCards normalizer correctly hides the resulting Side-A rotated card as `{name: "HIDDEN", stackSize: N}`, so adding an identifier to that projection would violate the existing privacy contract.

The game-service translation is the controlled boundary for typed DragnCards actions. The pinned upstream backend and plugin are submodules that this repository does not modify. DragnLang supports filtering authoritative `cardById` records and iterating them, so cleanup can happen inside the engine action without asking a caller to identify a hidden card.

## Goals / Non-Goals

**Goals:**

- Make the typed DragnCards villain-end transition clean all cards marked by the engine as boost cards before the existing phase transition.
- Reset only transient boost state and move marked cards to `sharedEncounterDiscard`, with no identity-bearing log operation.
- Avoid relying on normalized `HIDDEN` entries, stack order, or caller-provided hidden identifiers.
- Pin translation shape and privacy behavior with focused regression tests while leaving Marvel LCG behavior unchanged.

**Non-Goals:**

- Changing the normalized hidden-card shape or Marvel LCG ACL rules.
- Modifying the upstream DragnCards backend or plugin submodules.
- Changing orchestrator scheduling, provider reasoning, or adding a caller-facing hidden-card cleanup endpoint.
- Generalizing cleanup to arbitrary face-down cards that are not authoritatively marked as boosts.

## Decisions

### Decision 1: Cleanup in the typed villain-end translation

`VillainEndPhaseAction` will translate to a two-part DragnLang action list: first a `FOR_EACH_VAL` over `FILTER_CARDS` where the card's authoritative `boost` field is true, then the existing `ACTION_LIST villainEndPhase`. For each matched card, the list clears `rotation`, `tokens`, and `boost`, and moves it to `sharedEncounterDiscard` unless it is already there. The existing plugin action remains responsible for changing round and phase state.

**Alternative rejected: change the normalizer to emit hidden card identifiers.** This would make the card addressable to clients by leaking information the state contract explicitly hides, and would still leave the board uncleared.

**Alternative rejected: infer the first card in an engaged stack.** Stack order is not an identity contract; it can contain unrelated cards and would mutate the wrong card after a reorder.

**Alternative rejected: add a separate manual cleanup endpoint/action.** A caller could fail to invoke it, which would preserve the reported silent inconsistency. Making cleanup part of the existing phase transition gives the workflow one authoritative boundary.

**Alternative rejected: modify the pinned plugin's `villainEndPhase` JSON.** The repository treats the upstream plugin as an unmodified submodule, and a local gitlink commit would not be reproducible by the integration checkout. Keeping the compatibility operation in game-service preserves the pinned dependency.

### Decision 2: Select only authoritative boost records and never call identity-logging discard automation

The filter uses the engine's explicit boolean `boost` marker over `cardById`; it does not consume normalized state. Cleanup uses direct `SET` and `MOVE_CARD` operations rather than the plugin `DISCARD_CARD` function because that function logs the card's face name and can expose a hidden identity. Cards already in the encounter discard are not moved again, but their transient marker and state are still cleared.

**Alternative rejected: call `DISCARD_CARD` for each match.** Its existing implementation logs `currentFace.name`, which is an identity disclosure for a facedown boost card and is unnecessary for this cleanup.

**Alternative rejected: clear only cards whose group is `<player>Engaged`.** A card may already have been manually moved to the discard while retaining the stale boost marker; filtering by the marker and handling an already-discarded card repairs both states without guessing a location.

### Decision 3: Keep Marvel projection and ACL code untouched

Regression coverage will assert existing DragnCards hidden normalization and existing Marvel per-seat normalization behavior, but no Marvel source or shared hidden-card projection rules will change. The translated cleanup is emitted only by the DragnCards typed action path, and the platform driver continues to route marvel-lcg through its enumerated option surface.

**Alternative rejected: add a generic cross-platform cleanup primitive.** The two engines have different move surfaces and privacy models; widening a neutral action would violate the platform seam and risk changing Marvel ACL behavior.

## Risks / Trade-offs

- **[Risk]** DragnCards evaluates the cleanup and phase transition in one WebSocket action, and an upstream evaluator change could reject one of the inline operations. **Mitigation:** retain the existing named action list as the final operation, test the exact generated payload, and let the existing action error/state refresh path surface a rejected action.
- **[Risk]** A malformed or legacy card with `boost` set to a non-boolean truthy value could be selected. **Mitigation:** the authoritative marker is the plugin's own persisted property; tests require the predicate to be the marker and never a position or hidden count. No card identity leaves the action response.
- **[Risk]** `MOVE_CARD` may encounter a stale boost record that is no longer present in a group. **Mitigation:** the cleanup is limited to engine card records and the existing platform error path reports an actionable action rejection instead of claiming a successful transition; already-discarded records skip the move.
- **[Risk]** Calling the plugin UI hotkey or raw DragnLang action directly still bypasses the game-service typed translation. **Mitigation:** this change scopes the contract to the game-service DragnCards workflow and leaves raw upstream behavior explicit; raw actions remain a debug-only surface excluded from MCP.

## Migration Plan

No data migration is required. Deploy the game-service code and use the existing typed villain-end action; the next villain-end transition repairs any boost-marked cards still present in engine state before advancing. Rollback is a game-service code rollback; no persistent schema or plugin artifact changes are made.
