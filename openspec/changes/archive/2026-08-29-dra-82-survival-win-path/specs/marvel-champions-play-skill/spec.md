## MODIFIED Requirements

### Requirement: Skill provides an observable-driven turn procedure

The skill SHALL define a repeatable turn procedure that begins by reading normalized state, decides between hero and alter-ego form, sequences legal plays and basic powers, and ends by reporting rather than advancing the phase. Its prioritisation SHALL use the explicit main-scheme threat clock, the complete remaining villain-stage damage path, every hero's remaining health, the board's obligations, and the resources available to the team. A current-stage damage line SHALL NOT be called a credible victory race until remaining villain stages and their required hit points are visible or explicitly looked up.

#### Scenario: Turn begins with a state read
- **WHEN** the skill describes starting a turn
- **THEN** the first step SHALL be reading normalized game state and identifying the agent's own player identifier and zones

#### Scenario: Turn ends without phase advancement
- **WHEN** the skill describes finishing a turn
- **THEN** it SHALL instruct the agent to report that its turn is complete and leave phase advancement to the coordinating agent or human

#### Scenario: Threat pressure is computed from observables
- **WHEN** the skill describes choosing between thwarting and attacking
- **THEN** the heuristic SHALL use the explicit main-scheme threat clock, complete villain-stage path, and hero survival values rather than current-stage HP alone

#### Scenario: Threat pressure changes the action plan
- **WHEN** a newly observed threat effect, changed main-scheme threat, changed villain stage, changed hero health, or changed available resource changes the comparison
- **THEN** the player agent SHALL recompute the comparison and replan threat control, survival, or villain damage before taking or reporting the next action

#### Scenario: The turn plan accounts for the full villain path and team survival
- **WHEN** a player agent chooses between villain damage, threat control, and a survival line
- **THEN** it SHALL compare the legal damage available from the current board and resources with the explicit threat clock, all known remaining villain-stage hit points, and every hero's remaining health
- **AND** it SHALL replan when any of those inputs or the board changes

## ADDED Requirements

### Requirement: The villain damage race includes every remaining stage

The strategy reference SHALL identify the active villain as `zones.sharedVillain[0]` and SHALL calculate its current-stage remaining hit points as authoritative current-stage `villainHitPoints` minus the active card's sparse `tokens.damage`. It SHALL treat `villainHitPoints` as a current-stage total only, never as cumulative victory damage. It SHALL identify later stages from visible authoritative entries in the normalized villain-deck zone or from an explicit card/rules lookup for the known scenario and SHALL add each known later stage's required hit points separately, because excess damage does not carry between stages. A missing, hidden, non-numeric, or incomplete stage value SHALL remain unknown and SHALL prevent an exact full-path victory claim rather than being replaced with zero or a familiar-scenario guess.

#### Scenario: Rhino I is not the whole victory race
- **WHEN** normalized state reports Rhino I with `villainHitPoints = 19`, no current-stage damage, and a visible or explicitly looked-up Rhino II with 15 hit points remaining
- **THEN** the strategy SHALL treat the known damage required for victory as 34 across two stages
- **AND** it SHALL not describe 19 damage as sufficient for victory

#### Scenario: A hidden later stage keeps victory distance unknown
- **WHEN** the current villain stage has an authoritative current-stage total but the later villain deck is represented only by a `HIDDEN` entry or lacks a required stage hit-point value
- **THEN** the strategy SHALL report the later-stage requirement as unknown
- **AND** it SHALL refuse to claim an exact full-villain victory distance or safe damage race

#### Scenario: Terminal mode overrides stale race reports
- **WHEN** normalized state reports `mode=win` or `mode=loss`
- **THEN** the strategy SHALL stop race and survival planning and treat that terminal mode as authoritative
- **AND** it SHALL not continue acting because a stale damage or threat report suggests another line

### Requirement: Hero health is a team-survival input without inventing defeat

The strategy reference SHALL compute each seated hero's remaining health from the normalized player's authoritative maximum and the identity card's explicit sparse `tokens.damage`, using only numeric values that are present in `players` and `zones`. It SHALL treat a hero with positive but low remaining health as a major team-risk input, not as defeated; only an authoritative zero-or-less remaining value or terminal `mode=loss` establishes defeat. It SHALL use explicit incoming attack or scheme values, explicit defensive/healing options, the threat clock, and available resources to compare expected team loss against the value of continuing the damage race. Missing health, damage, incoming values, or resource facts SHALL be reported as unknown rather than guessed.

#### Scenario: Near-death hero triggers a survival comparison
- **WHEN** a hero has positive remaining health at or below an explicitly known incoming villain or minion attack and the team has an explicit legal defend, heal, ally-block, or alter-ego line
- **THEN** the strategy SHALL evaluate that line before spending resources on the damage race
- **AND** when the expected team loss outweighs the race value, it SHALL choose survival planning while stating that the hero is still alive rather than declaring automatic game over

#### Scenario: A low-health hero is not silently ignored
- **WHEN** a hero has positive remaining health but the next villain phase can defeat that hero on the known board and the current race cannot finish the complete known villain path before that window
- **THEN** the strategy SHALL replan to preserve the hero or control threat
- **AND** it SHALL not continue the current-stage damage line merely because the villain has low current-stage hit points

#### Scenario: Unknown survival inputs do not become safety
- **WHEN** a hero's remaining health, incoming damage, or the resource cost of a survival line is missing or non-numeric
- **THEN** the strategy SHALL name the missing input and refuse to call the hero safe or the damage race credible
- **AND** it SHALL request an explicit value or use only a line whose legality and outcome are already explicit

### Requirement: An incredible race switches to survival or threat control

The strategy SHALL call a villain race credible only when every remaining stage needed for victory is known and the board's explicit legal damage and available resources can complete that path before the next relevant threat or team-survival loss window. It SHALL account for current main-scheme and side-scheme effects, engaged minions, hero health, defense/healing resources, and the minimum next-villain-phase threat when comparing the race. When the complete race is not credible, or when the expected team loss is greater than the race value, it SHALL switch to the highest-value legal survival or threat-control line and SHALL report the current-state reason. It SHALL not turn unknown damage, threat, stage health, or resources into an optimistic estimate.

#### Scenario: A race that cannot finish in time yields to survival and threat control
- **WHEN** the known full-villain damage path takes longer than the explicit threat clock or a known hero-survival loss window
- **THEN** the strategy SHALL stop treating villain damage as the primary plan
- **AND** it SHALL prioritize an explicit survival or threat-control action, preserving resources for defense or recovery when that is the legal higher-value line

#### Scenario: A credible complete race may continue after safety checks
- **WHEN** every remaining villain stage is known, the legal damage line can finish before the explicit threat and survival windows, and no side-scheme or minion obligation has a higher explicit consequence
- **THEN** the strategy SHALL be allowed to continue the damage race
- **AND** it SHALL still re-read normalized state after a meaningful board change and recompute the full-path comparison
