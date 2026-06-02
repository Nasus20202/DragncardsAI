## 1. State Simplifier Function

- [ ] 1.1 Add `_simplify_marvel_state(raw_state: dict) -> dict` private utility function to `game_state.py`
- [ ] 1.2 Extract roundNumber, mode, villainHitPoints from game state
- [ ] 1.3 Build players dict filtering null aliases and including hitPoints/handSize
- [ ] 1.4 Extract cards from cardById into zone arrays (visible cards only)
- [ ] 1.5 Include card fields: id, instanceId, name, currentSide, exhausted, tokens

## 2. API Integration

- [ ] 2.1 Add `format` query parameter to `GET /games/{id}/state` endpoint
- [ ] 2.2 Detect Marvel Champions plugin and apply simplification when `?format=simplified`
- [ ] 2.3 Add unit tests for simplified state transformation with mock data
- [ ] 2.4 Add unit test for raw state passthrough (default, non-Marvel, or no format param)