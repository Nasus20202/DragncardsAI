## Context

The game-service already has `ZeroTokensAction` which clears all tokens from a card. However, Marvel Champions gameplay frequently requires adding or removing specific amounts of tokens (e.g., removing 1 threat from a scheme, adding 2 damage to an enemy, removing stunned/confused status). The DragnCards Web UI exposes Token Hotkeys for this, but there's no typed endpoint.

## Goals / Non-Goals

**Goals:**
- Add typed `ModifyTokensAction` for adding/removing tokens with specific amounts
- Use `INCREASE_VAL` DragnLang operation (supports negative amounts for removal)
- Include Marvel Champions-specific token type enum

**Non-Goals:**
- No bulk operations across multiple cards
- No token validation beyond DragnCards' own behavior
- No UI changes

## Decisions

### Decision: Use INCREASE_VAL instead of SET
We use `INCREASE_VAL` because it supports both positive (add) and negative (remove) amounts. `SET` would require reading the current value first to compute a new value.
- **Alternative**: `SET` on tokens object — rejected because it requires read-modify-write cycle
- **Rationale**: `INCREASE_VAL` is atomic and handles negatives natively

### Decision: Token type as string enum with Marvel Champions defaults
- **Alternative 1**: Generic string — allows any token type but no validation
- **Alternative 2**: Numeric enum — too rigid for plugin variations
- **Rationale**: String enum provides validation while allowing flexibility for future plugins. Default values cover MC core set tokens (threat, damage, stunned, confused, toughness).

### Decision: Single endpoint for all token modifications
- **Alternative**: Separate endpoints for each token type — rejected as too verbose
- **Rationale**: One endpoint with `token_type` parameter is simpler and follows existing patterns (e.g., `set_card_property` takes a property path)

## Risks / Trade-offs

- **Risk**: DragnCards may not recognize unfamiliar token types
  - **Mitigation**: Documentation lists known MC token types; callers can use `raw` action for experimental types

- **Risk**: Negative amounts on non-existent tokens may cause errors
  - **Mitigation**: DragnCards `INCREASE_VAL` handles this gracefully (treats as 0 + negative = negative)