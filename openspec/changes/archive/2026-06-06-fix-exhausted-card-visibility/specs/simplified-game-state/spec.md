## MODIFIED Requirements

### Requirement: Simplified state hides facedown cards
The Game Service SHALL hide cards only when they are truly facedown (identity concealed from players), not when exhausted. Exhausted cards remain visible.

#### Scenario: Simplified state hides facedown cards
- **WHEN** a card has `rotation != 0` AND is facedown (identity concealed)
- **THEN** the card SHALL be hidden as "HIDDEN" with `id` and `instanceId` masked

#### Scenario: Simplified state shows exhausted cards
- **WHEN** a card is on Side B (exhausted)
- **THEN** the card SHALL be visible with its name and details intact
- **AND** the `exhausted` field SHALL be true

#### Scenario: Simplified state does not hide exhausted cards
- **WHEN** a card has `rotation != 0` but is on Side B (exhausted)
- **THEN** the card SHALL remain visible (not hidden)
- **AND** the `exhausted` field SHALL be true
- **AND** the `currentSide` SHALL be "B"