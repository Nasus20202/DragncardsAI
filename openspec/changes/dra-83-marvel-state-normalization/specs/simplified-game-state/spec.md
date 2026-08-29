# Marvel state normalization corrections

## ADDED Requirements

### Requirement: Marvel state carries authoritative current values and active schemes

For marvel-lcg, every scalar and card value included in the platform-neutral state projection
SHALL come from the engine's current world descriptor. The projection SHALL omit an
unavailable numeric fact rather than substitute a value that changes its meaning.

The marvel-lcg projection SHALL expose the active main scheme in `sharedMainScheme`, active
side schemes in `sharedSideSchemes`, and the active villain in `sharedVillain`. Visible scheme
cards SHALL carry a sparse `tokens.threat` value equal to the engine's current threat counter.
Side-scheme cards SHALL retain their public effect indicators under canonical token names,
including `crisis`, `hazard`, and `acceleration` when reported by the engine.

#### Scenario: A Rhino checkpoint preserves the current villain health

- **WHEN** a visible Rhino I descriptor reports current `info.health` as `19`
- **THEN** the normalized state SHALL report `villainHitPoints` as `19`
- **AND** the state SHALL not report the villain as defeated solely because a world-level villain HP field is absent

#### Scenario: An unavailable villain health value is omitted

- **WHEN** the active villain descriptor has no authoritative current health value
- **THEN** the normalized state SHALL omit `villainHitPoints`
- **AND** the state SHALL not synthesize `villainHitPoints` as `0`

#### Scenario: Main-scheme threat uses the neutral token name

- **WHEN** the engine reports main-scheme checkpoints with current threat and target values of `9/14`, `12/14`, and `14/14`
- **THEN** `sharedMainScheme[0].tokens.threat` SHALL equal `9`, `12`, and `14` respectively
- **AND** the engine's target-threat metadata SHALL remain available without replacing the current `threat` value

#### Scenario: Active side schemes remain visible with their effects

- **WHEN** `area_schemes_side` contains active visible Crowd Control, Breakin' & Takin', and Highway Robbery descriptors
- **THEN** `sharedSideSchemes` SHALL contain those named cards
- **AND** each card SHALL retain its current public `threat` value
- **AND** Crisis, Hazard, and acceleration indicators reported by the engine SHALL be exposed as `tokens.crisis`, `tokens.hazard`, and `tokens.acceleration`

### Requirement: Marvel engine phases have neutral classifications

The marvel-lcg normalizer SHALL classify every phase in the engine's phase state vocabulary
without rewriting the original text in `phaseLabel`. Initialization and mulligan phases
SHALL classify as `setup`; Player Turn and Player Turn End SHALL classify as `player`; Main
Scheme Place Threat, Enemy Activation, Deal Encounter Cards, and Reveal Encounter Cards
SHALL classify as `villain`; and End Phase, End Round, and Start Round SHALL classify as
`passive`. A phase outside that vocabulary SHALL remain `unknown`.

#### Scenario: Enemy activation is a villain phase

- **WHEN** the engine reports `phase` as `Enemy Activation`
- **THEN** the normalized state SHALL report `phase` as `villain`
- **AND** SHALL preserve `phaseLabel` as `Enemy Activation`

#### Scenario: Every valid Marvel villain step is classified

- **WHEN** the engine reports Main Scheme Place Threat, Enemy Activation, Deal Encounter Cards, or Reveal Encounter Cards
- **THEN** the normalized state SHALL report `phase` as `villain` for each value

#### Scenario: Unknown Marvel phase remains explicit

- **WHEN** the engine reports a phase text outside its known phase vocabulary
- **THEN** the normalized state SHALL report `phase` as `unknown`
- **AND** SHALL preserve that text in `phaseLabel`
