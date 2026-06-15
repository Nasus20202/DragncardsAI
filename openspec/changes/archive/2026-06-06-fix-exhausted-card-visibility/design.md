## Context

Marvel Champions represents exhausted cards visually by flipping them to Side B and applying a rotation. However, this is **visible information** - both players can see which card is exhausted and what it is. The current `_simplify_marvel_state` function incorrectly uses `rotation != 0` as the condition for hiding cards, conflating exhausted cards (Side B with rotation) with truly hidden/facedown cards.

## Goals / Non-Goals

**Goals:**
- Exhausted cards (Side B) remain visible in the simplified state output
- The `exhausted` field correctly reflects the card's exhaustion state
- Only truly facedown cards (where the identity is concealed) are hidden

**Non-Goals:**
- Changing how exhausted cards work in the game
- Modifying the DragnCards backend behavior

## Decisions

### D1: Remove rotation check, keep player/encounter check for hiding
- **Choice**: Only hide cards when `cardName in ("player", "encounter")`, not based on `rotation`
- **Rationale**: Exhausted cards are visible; `rotation` changes for both facedown AND exhausted cards
- **Alternatives rejected**:
  - Check `rotation` only for certain conditions - would require understanding DragnCards internal state model

### D2: Keep exhausted field for Side B cards
- **Choice**: The `exhausted` boolean will be true for cards on Side B
- **Rationale**: This gives LLMs the information they need for decision-making
- **Alternatives rejected**:
  - Ignore exhaustion state entirely - loses important game state info

## Risks / Trade-offs

- **DragnCards state model uncertainty**: We're inferring that `rotation != 0` doesn't mean "hidden" - if this assumption is wrong, cards might appear when they shouldn't
- **Mitigation**: Integration testing with real DragnCards instances to verify behavior