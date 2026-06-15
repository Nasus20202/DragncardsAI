## Context

The game state JSON returns card instances with `instanceId` as the unique identifier for each card. The `MoveCardAction` and `SetCardPropertyAction` models currently use `card_id` for their parameters, creating a naming inconsistency. Users must mentally map between the two when crafting actions based on observed state.

## Goals / Non-Goals

**Goals:**
- Make the action parameter names consistent with the game state JSON field (`instanceId`)

**Non-Goals:**
- Changing the DragnLang wire format (which still uses card ID concept)

## Decisions

### Rename `card_id` to `instance_id` in MoveCardAction and SetCardPropertyAction

- **Why**: The parameter identifies which card to act on. Cards in DragnCards are identified by `instanceId` in the game state JSON, so `instance_id` accurately matches that field name.
- **Alternative**: Keep `card_id` - Rejected because it creates cognitive overhead for users who see `instanceId` in state

## Risks / Trade-offs

- **Breaking change**: Existing code that uses `card_id` will fail - mitigated by clear error messages and quick adoption
- The DragnLang wire format still expects a card identifier in the first argument position; the parameter rename is only a naming change on our side, not a protocol change