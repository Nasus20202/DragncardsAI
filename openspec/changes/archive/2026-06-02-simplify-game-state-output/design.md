## Context

The Game Service receives a deeply nested JSON state from the DragnCards backend via Phoenix Channels. The `get_game_state` endpoint returns this raw state structure, which includes:
- Full `cardById` dictionary with all card properties including sides, tokens, attachments
- Redundant zone/group metadata in separate structures
- Internal identifiers and state that LLM agents don't need

This makes it hard to efficiently prompt LLMs without excessive token usage or complex parsing logic in each agent implementation.

## Goals / Non-Goals

**Goals:**
- Provide a simplified, flat representation of Marvel Champions game state
- Include only information relevant for LLM decision-making (players, zones with visible cards, round/mode, key counters)
- Always simplified for Marvel Champions (no opt-in needed)

**Non-Goals:**
- Do NOT modify the DragnCards backend or plugin
- Do NOT change the core game action execution semantics
- Do NOT support all DragnCards plugins - Marvel Champions specific

## Decisions

### D1: Add simplified state transformer function
- **Choice**: Add `_simplify_marvel_state(raw_state: dict) -> dict` private utility function directly in `game_service/api/routers/game_state.py`
- **Rationale**: No new file needed; keeps transformation close to where state is consumed; straightforward for this small function
- **Alternatives rejected**:
  - Dedicated module (`state_simplifier.py`) - unnecessary indirection for a single function

### D2: Always simplified for Marvel Champions
- **Choice**: Transform state automatically for Marvel Champions sessions (no query parameter needed)
- **Rationale**: The simplified output is the desired behavior for LLM agents; no reason to expose raw nest structure
- **Alternatives rejected**:
  - Query parameter `?format=simplified` - adds API surface for no benefit
  - Raw state for everyone - defeats purpose of the simplification

### D3: Filter to visible top-level cards only
- **Choice**: Only include cards whose `stackId` equals their own `card_id` (no tucked attachments)
- **Rationale**: LLMs need to reason about visible game objects; attachment hierarchy is rarely relevant for strategic decisions
- **Alternatives rejected**:
  - Include all cards with attachment relationships - increases token count, adds complexity

### D4: Flatten zone structure
- **Choice**: Output `zones` as `Dict[str, List[card_dict]]` instead of separate zone metadata
- **Rationale**: Simpler for LLM to iterate; matches natural mental model of "where are the cards"
- **Alternatives rejected**:
  - Mirror exact DragnCards group structure - defeats purpose of simplification

### D5: Player data minimal
- **Choice**: Only include `hitPoints` and `handSize` per player (skip alias if null as in reference script)
- **Rationale**: Reduces noise while preserving decision-relevant stats
- **Alternatives rejected**:
  - Full player data - unnecessary for most bot decisions

### D6: No schema validation on simplified output
- **Choice**: Return Python dict; let FastAPI serialize to JSON
- **Rationale**: Output is derived from trusted internal state; validation overhead not justified
- **Alternatives rejected**:
  - Pydantic response model - adds complexity without value

## Risks / Trade-offs

- **Schema drift**: If DragnCards changes state structure, transformer breaks → Mitigation: unit tests with example payloads, graceful fallback to raw state on error
- **Marvel Champions specific**: This solution is tailored to MC state shape → Mitigation: keep transformer in plugin-aware module; extend pattern for other plugins later
- **Loss of information**: Some card properties omitted → Mitigation: include most relevant (name, exhaust, tokens, databaseId); LLMs can request raw state if needed