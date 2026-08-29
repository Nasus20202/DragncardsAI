## MODIFIED Requirements

### Requirement: The skill provides an observable-driven turn procedure

The skill SHALL define a repeatable player-turn procedure that begins with a fresh normalized state read, inspects the active main scheme and every active shared side scheme before selecting attack or threat control, and ends by reporting rather than advancing the phase. The procedure SHALL use `playRound`, `phase`, `players`, and `zones` as authoritative normalized values; it SHALL use the active main scheme at `zones.sharedMainScheme[0]`, its sparse `tokens.threat` value, and the active side schemes at `zones.sharedSideSchemes` when those entries are present. A missing optional token key SHALL mean zero, but a missing required card, target, or gain SHALL remain unknown.

Before ending the player phase, the skill SHALL recompute the next villain-phase minimum threat from the current main-scheme threat, explicit base placement, explicit acceleration, and known scheme contributions from enemies activating against players in alter-ego form. It SHALL compare that projection with the explicit target threat and SHALL replan threat control versus villain damage whenever the projection, target, side-scheme effects, or available thwart changes. If the target or any required gain is unavailable, the skill SHALL state exactly what is unknown and SHALL refuse to guess or present an exact clock.

#### Scenario: A turn starts with normalized side-scheme review
- **WHEN** a player agent begins a turn with `zones.sharedMainScheme` and `zones.sharedSideSchemes` in its normalized state
- **THEN** it SHALL read the main scheme's current `tokens.threat` and inspect every active side scheme's sparse `tokens` before choosing attack or thwart
- **AND** it SHALL not treat the side schemes as a single generic threat total

#### Scenario: Threat pressure changes the action plan
- **WHEN** a newly observed side-scheme acceleration, changed main-scheme threat, changed target, or changed available thwart changes the next-villain-phase projection
- **THEN** the player agent SHALL recompute the projection and replan threat control versus villain damage before taking or reporting the next action

#### Scenario: The 9/14 checkpoint is an immediate warning
- **WHEN** the current main-scheme state is `9/14` and the explicit minimum next-villain-phase gain is `5`
- **THEN** the player agent SHALL report that the minimum next-villain-phase threat reaches `14/14` and flag deterministic main-scheme lethal-risk before ending the player phase
- **AND** it SHALL not report the player phase complete while silently choosing a damage line that leaves that risk unexplained

## ADDED Requirements

### Requirement: Active normalized side schemes are ranked by their reported effects

The strategy reference SHALL require the player agent to enumerate every visible card in `zones.sharedSideSchemes` and rank cards using only public, non-zero effect indicators in each card's sparse `tokens`. The ranking SHALL distinguish `crisis` (player cards cannot remove threat from the main scheme), `hazard` (extra encounter pressure), `acceleration` (additional main-scheme threat placement), explicit hand or resource denial indicators, and current `threat`. The agent SHALL use the actual reported value and current clock to choose between effects, SHALL preserve a named card's current threat, and SHALL not invent an effect from a card name or hidden text.

A Crisis side scheme SHALL be treated as a blocker whenever the current plan needs player-card threat removal from the main scheme; side-scheme threat remains a legal threat-control target while Crisis is active. Acceleration that is explicitly reported as applying to the main scheme SHALL be included in the next-placement projection. Hazard and denial SHALL be reported as pressure without converting them into unreported damage, card counts, or resources.

#### Scenario: Multiple side schemes retain distinct priorities
- **WHEN** normalized state exposes multiple active side schemes with distinct `tokens.crisis`, `tokens.hazard`, `tokens.acceleration`, and `tokens.threat` values
- **THEN** the strategy SHALL name each card, retain each card's effect values, and rank the cards by their actual clock or action-blocking consequence
- **AND** it SHALL be able to identify an explicit acceleration card separately from a hazard card and a current-threat-only card

#### Scenario: Crisis blocks main-scheme threat removal
- **WHEN** any active side scheme has a non-zero `tokens.crisis` value and a player-card plan would remove threat from the main scheme
- **THEN** the strategy SHALL identify that main-scheme removal as blocked, prioritize clearing or otherwise resolving the Crisis side scheme, and direct available threat control to an eligible side scheme when useful

#### Scenario: An effect absent from normalized state is not inferred
- **WHEN** a side scheme has no explicit indicator for hazard, acceleration, hand denial, or resource denial
- **THEN** the strategy SHALL not claim that effect merely from the card name or remembered card text
- **AND** it SHALL rank only the effects and current threat that are observable or explicitly looked up

### Requirement: The threat clock uses explicit minimum inputs and reports uncertainty

The strategy reference SHALL define the minimum next-villain-phase main-scheme threat as:

`current main-scheme threat + explicit base placement + explicit acceleration that applies to the main scheme + known enemy scheme contributions against players currently in alter-ego form`.

The current threat SHALL come from `zones.sharedMainScheme[0].tokens.threat`, with a missing sparse token treated as zero only when the active main-scheme card is present. Base placement, acceleration, enemy scheme values, and the target SHALL be taken only from normalized state, an explicit prompt/coordinator value, or an explicit card/rules lookup. Hidden boost cards and unavailable printed values SHALL not be guessed. The result SHALL be labeled a minimum because unknown later villain effects can only increase the actual total; when any required input is unknown, the agent SHALL report the missing input and SHALL not claim an exact projected clock or target comparison.

#### Scenario: Explicit inputs produce a minimum projection
- **WHEN** current main-scheme threat, target threat, base placement, acceleration, and every known alter-ego enemy scheme contribution are explicit numeric values
- **THEN** the strategy SHALL add those values and compare the minimum next-villain-phase threat with the target
- **AND** it SHALL separately identify unknown boost or card effects rather than adding guessed values

#### Scenario: An unknown target or gain stops exact planning
- **WHEN** the active main scheme, its target threat, base placement, acceleration, or a required alter-ego scheme contribution is missing or non-numeric
- **THEN** the player agent SHALL name the missing value, ask the coordinator or human or perform the permitted explicit lookup, and refuse to guess an exact next-phase clock
- **AND** it SHALL not claim that the main scheme is safe merely because a guessed default would be below target

### Requirement: Deferred side schemes carry a current-state reason

Whenever the player agent defers an active side scheme, its report SHALL name the scheme, its current observable threat and effect indicators, and a reason tied to the current state, such as an explicit blocker, an insufficient current thwart budget, or a named higher-ranked clock risk. A generic statement that the scheme will be handled later SHALL not satisfy the strategy checklist. Before reporting the turn complete, the agent SHALL repeat the side-scheme ranking and next-phase projection after its final meaningful action.

#### Scenario: A deferred scheme is justified with current facts
- **WHEN** a side scheme remains active at the end of a player turn
- **THEN** the report SHALL state that scheme's current threat/effects and why the current board makes another action higher priority
- **AND** the report SHALL leave enough numeric or named facts for the coordinator to verify the deferral

#### Scenario: The final report flags deterministic lethal risk
- **WHEN** the final recomputation reaches or exceeds the explicit main-scheme target on its minimum projection
- **THEN** the player agent SHALL flag the next-phase lethal-risk before reporting completion
- **AND** it SHALL state whether Crisis or another side-scheme effect prevents the intended threat-control line
