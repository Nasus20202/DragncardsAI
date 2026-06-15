## 1. State Simplifier Function

- [x] 1.1 Add `_simplify_marvel_state(raw_state: dict) -> dict` private utility function to `game_state.py`
- [x] 1.2 Extract roundNumber, mode, villainHitPoints from game state
- [x] 1.3 Build players dict filtering null aliases and including hitPoints/handSize
- [x] 1.4 Extract cards from cardById into zone arrays (visible cards only)
- [x] 1.5 Include card fields: id, instanceId, name, currentSide, exhausted, tokens

## 2. API Integration

- [x] 2.1 Apply simplified output automatically for Marvel Champions sessions
- [x] 2.2 Detect Marvel Champions plugin and apply simplification
- [x] 2.3 Add unit tests for simplified state transformation with mock data
- [x] 2.4 Add unit test for raw state passthrough (non-Marvel plugins)