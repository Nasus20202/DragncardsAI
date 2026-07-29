## MODIFIED Requirements

### Requirement: Simplified Marvel Champions state output
The Game Service SHALL provide a simplified representation of Marvel Champions game state that includes only essential information for LLM decision-making, and the per-card payload SHALL be compact enough that the full state response stays under 256 KB for a 4-player table with a loaded encounter set so the response fits the MCP WebSocket transport limit (1,048,576 bytes).

#### Scenario: Simplified state filters to essential fields
- **WHEN** a client requests `GET /games/{id}/state` for a Marvel Champions session
- **THEN** the Game Service SHALL return a flattened representation containing `roundNumber`, `mode`, `villainHitPoints`, `stepId`, `stepDescription`, `players` (with hitPoints and handSize), and `zones`

#### Scenario: Simplified state omits default-valued card fields
- **WHEN** a visible card has `currentSide == "A"`, `exhausted == false`, or all seven token counters at zero
- **THEN** those fields SHALL be omitted from that card's emitted object
- **AND** a card with no meaningful `currentSide`, `exhausted` or `tokens` SHALL be emitted as just `{id, instanceId, name, stackSize}`

#### Scenario: Simplified state emits only non-zero token counters
- **WHEN** a card has any token counters greater than zero
- **THEN** the emitted `tokens` field SHALL contain only the keys whose values are non-zero
- **AND** if no token counter is non-zero, the `tokens` field SHALL be absent

#### Scenario: Simplified state collapses HIDDEN entries
- **WHEN** a zone contains one or more HIDDEN entries (face-down cards or player/encounter identity cards)
- **THEN** each HIDDEN entry SHALL be emitted as `{name: "HIDDEN", stackSize: N}` and SHALL NOT carry `id`, `instanceId`, `currentSide`, `exhausted`, or `tokens`

#### Scenario: Simplified state payload fits MCP transport
- **WHEN** the simplified state is generated for a 4-player table with a 40-card hero deck per seat, a loaded encounter set, the main scheme, the villain, and standard attachments
- **THEN** the JSON-serialized payload SHALL be under 256 KB
- **AND** SHALL remain under the 1,048,576-byte WebSocket message size limit with substantial headroom

#### Scenario: Simplified state excludes attachment hierarchy
- **WHEN** a card is an attachment tucked under another card
- **THEN** the simplified state SHALL NOT include that attachment as a separate entry in its zone's card list

#### Scenario: Simplified state omits null player aliases
- **WHEN** a player has a null alias in the raw state
- **THEN** that player SHALL be omitted from the simplified state's players object

#### Scenario: Simplified state shows stack size
- **WHEN** multiple cards share the same stackId in a zone
- **THEN** only the top card SHALL appear with `stackSize` indicating the total count

#### Scenario: Simplified state hides facedown cards but not exhausted
- **WHEN** a card has `rotation != 0` AND is on Side A (not exhausted)
- **THEN** the card SHALL be hidden as "HIDDEN" with merged stack size
- **BUT WHEN** a card is exhausted (Side B with `exhausted: true`), it SHALL remain visible

#### Scenario: Simplified state shows exhausted cards
- **WHEN** a card is on Side B (exhausted)
- **THEN** the card SHALL be visible with its name and details intact
- **AND** the `exhausted` field SHALL be present and true

#### Scenario: Simplified state does not hide exhausted cards
- **WHEN** a card has `rotation != 0` but is on Side B (exhausted)
- **THEN** the card SHALL remain visible (not hidden)
- **AND** the `exhausted` field SHALL be present and true
- **AND** the `currentSide` SHALL be present and equal to "B"

#### Scenario: Simplified state hides player/encounter cards
- **WHEN** a card's name is "player" or "encounter"
- **THEN** the card SHALL be hidden as "HIDDEN" with merged stack size

#### Scenario: Simplified state merges hidden cards
- **WHEN** multiple hidden cards (facedown or player/encounter) exist in the same zone
- **THEN** they SHALL be merged into a single "HIDDEN" entry with combined `stackSize`
