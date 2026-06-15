# Simplified Game State Spec

## Purpose

The simplified game state provides a streamlined representation of game state for LLM consumption, filtering out unnecessary details while preserving essential gameplay information.

## Requirements

### Requirement: Simplified Marvel Champions state output
The Game Service SHALL provide a simplified representation of Marvel Champions game state that includes only essential information for LLM decision-making.

#### Scenario: Simplified state filters to essential fields
- **WHEN** a client requests `GET /games/{id}/state` for a Marvel Champions session
- **THEN** the Game Service SHALL return a flattened representation containing only `roundNumber`, `mode`, `villainHitPoints`, `players` (with hitPoints and handSize), and `zones` (with visible cards including `id`, `instanceId`, `name`, `currentSide`, `exhausted`, `tokens`, `stackSize`)

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
- **THEN** the card SHALL be hidden as "HIDDEN" with `id` and `instanceId` masked
- **BUT WHEN** a card is exhausted (Side B with `exhausted: true`), it SHALL remain visible

#### Scenario: Simplified state shows exhausted cards
- **WHEN** a card is on Side B (exhausted)
- **THEN** the card SHALL be visible with its name and details intact
- **AND** the `exhausted` field SHALL be true

#### Scenario: Simplified state does not hide exhausted cards
- **WHEN** a card has `rotation != 0` but is on Side B (exhausted)
- **THEN** the card SHALL remain visible (not hidden)
- **AND** the `exhausted` field SHALL be true
- **AND** the `currentSide` SHALL be "B"

#### Scenario: Simplified state hides player/encounter cards
- **WHEN** a card's name is "player" or "encounter"
- **THEN** the card SHALL be hidden as "HIDDEN" with `id` masked

#### Scenario: Simplified state merges hidden cards
- **WHEN** multiple hidden cards (facedown or player/encounter) exist in the same zone
- **THEN** they SHALL be merged into a single "HIDDEN" entry with combined `stackSize`
- **AND** `instanceId` and `currentSide` SHALL be inherited from the first card in `groupById.{zone}.stackIds`