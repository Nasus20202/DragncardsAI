## Why

The DragnCards `drawBoost` action moves a face-down encounter card into a player's engaged zone and marks it as a boost, but the plugin's villain-phase end action advances the phase without returning those boost cards to the encounter discard. The next normalized state therefore contains an unaddressable `HIDDEN` entry and the player agent cannot safely repair the board; the cleanup must happen from authoritative engine metadata without exposing the card identity.

## What Changes

- Make the DragnCards villain-phase transition clean up every engine card explicitly marked as a boost before entering the next player phase.
- Reset the boost card's transient orientation, tokens, and boost marker while moving it to the shared encounter discard, without logging or returning its identity.
- Keep the existing normalized `HIDDEN` projection and Marvel LCG per-seat hidden-card ACL behavior unchanged.
- Add focused regression coverage for the translated `draw_boost`/villain-end sequence, cleanup targeting by the authoritative boost flag rather than stack position, and hidden-card privacy across DragnCards and Marvel state projections.

## Capabilities

### New Capabilities

### Modified Capabilities

- `openspec/specs/dragncards/spec.md`: DragnCards action execution must make boost-card cleanup authoritative at villain-phase completion without leaking hidden card identity.

## Impact

- `services/game-service/src/game_service/logic/actions.py`: DragnCards translation for `VillainEndPhaseAction` will prepend an inline, server-side boost cleanup operation to the existing plugin phase transition.
- `services/game-service/tests/unit/test_action_translation.py` and focused state tests: verify the operation shape, authoritative predicate, and privacy invariants.
- `openspec/changes/dra-92-dragncards-hidden-card/`: proposal, delta spec, design, and implementation tasks.
- No changes to orchestrator turn scheduling, provider reasoning, or Marvel LCG normalization/ACL semantics.

