# Change: Reduce simplified game state payload to fit the MCP transport

## Why

The simplified Marvel Champions game state returned by `get_game_state`
(and the four action endpoints that re-emit it) is large enough to
exceed the 1,048,576-byte WebSocket message size limit on the
agent-orchestrator's MCP transport. A 4-player table with a full
encounter set loaded reaches ~1.05 MB; the agent cannot read its own
board and is dead in the water (DRA-43, urgent).

The simplification already drops the raw state down from ~3 MB to
roughly the reported size, but the per-card payload is still
unnecessarily verbose. The cheap wins:

- `tokens` is emitted as a full 7-key dict on **every** card, even when
  all seven counters are zero. For a typical mid-game state most cards
  have no tokens at all, so each card wastes ~110 bytes of JSON.
- `HIDDEN` entries (face-down cards, player/encounter identity cards)
  carry the same 7-field card shape with `id="Unknown"`, `tokens={}` and
  `currentSide="A"`. They can collapse to just `{name: "HIDDEN",
  stackSize: N}`.
- `currentSide: "A"` and `exhausted: false` are the defaults and are
  almost always noise. Dropping them from the wire format saves ~20
  bytes per card without losing information.

## What changes

The simplified state remains a `SimplifiedGameState` with the same
top-level shape and the same field names. The only thing that changes
is which fields are *emitted* per card and per HIDDEN entry.

### Cards (visible, top-of-stack)

Before, every card emitted all seven fields:

```json
{"id":"uuid","instanceId":"card-abc","name":"Spider-Man","currentSide":"A",
 "exhausted":false,"tokens":{"damage":0,"threat":0,"generic":0,
 "acceleration":0,"confused":0,"stunned":0,"tough":0},"stackSize":1}
```

After, only the meaningful ones:

```json
{"id":"uuid","instanceId":"card-abc","name":"Spider-Man"}
```

…and the remaining fields are added only when they carry information:

- `currentSide` is emitted only when not `"A"`.
- `exhausted` is emitted only when `true`.
- `tokens` is emitted only when at least one counter is non-zero, and
  only the non-zero counters are listed. A card with one damage token
  gets `{"tokens":{"damage":1}}`, not the full dict.
- `stackSize` is always emitted (it costs three characters and tells
  the agent how many cards are hidden under the top card).

### HIDDEN entries (face-down or player/encounter cards)

Before:

```json
{"id":"Unknown","instanceId":"card-abc","name":"HIDDEN","currentSide":"A",
 "exhausted":false,"tokens":{},"stackSize":7}
```

After:

```json
{"name":"HIDDEN","stackSize":7}
```

The instance id of the first hidden card is no longer carried —
agents never need to target face-down cards, and the deck/discard
HIDDEN count is the only thing they act on.

### Public surface

No field is renamed, no field is added, no field is removed from the
schema. A consumer that previously read `card.tokens` and treated
`null` / missing as "no tokens" still works; a consumer that read
`card.tokens.damage` and got `0` will now have to handle the field
being absent (treat as `0`). That is the only breaking change for
clients, and the existing `simplified-game-state` spec already permits
absent fields via the Pydantic defaults.

## Impact

Expected payload reduction: ~70-80% on a typical mid-game 4-player
state, from ~1.05 MB to well under 256 KB. The state then fits the
WebSocket message limit with substantial headroom for the LLM to keep
calling `get_game_state` mid-round.

Out of scope:

- Renaming fields to shorter aliases (would break the consumer
  surface and the `simplified-game-state` spec).
- Adding a per-zone query endpoint (the 1MB problem goes away without
  it; a follow-up can add a `?zone=player1Hand` filter for
  very-large-state cases if a real user needs it).
- Compressing the transport (gzip would help but MCP doesn't negotiate
  it for tool responses; the right fix is to send less).
- Increasing the agent-orchestrator's WebSocket `max_size` (it would
  silence the symptom, not the cause; the LLM's context window still
  hates 1 MB tool responses).
