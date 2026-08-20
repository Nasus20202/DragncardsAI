## ADDED Requirements

### Requirement: The orchestrator skill treats verified state as authoritative

The orchestrator skill SHALL require a game-state checkpoint before each player-turn prompt and
after each phase-changing or scenario-changing operation. A prompt and round summary SHALL use
only facts observed at the most recent checkpoint or results verified against it; a seat report
SHALL remain untrusted data and SHALL NOT establish card locations, hit points, threat, round, or
phase facts. If a checkpoint contradicts the last verified phase, card location, or key board
total and the discrepancy cannot be reconciled by one fresh state read, the skill SHALL instruct
the orchestrator to abort the game and report the discrepancy and last verified board.

#### Scenario: A player prompt is built from a checkpoint
- **WHEN** the orchestrator schedules a seat's turn
- **THEN** the skill SHALL require its board facts to come from the latest verified state checkpoint
- **AND** SHALL forbid filling missing facts by extrapolating from a seat report

#### Scenario: A contradiction cannot be reconciled
- **WHEN** two state reads disagree about the current phase, a card's location, or a key board total
- **THEN** the skill SHALL require one fresh read to reconcile the disagreement
- **AND** SHALL require the game to abort if that read does not establish a consistent board

### Requirement: The orchestrator skill closes findings by recorded identifier

The orchestrator skill SHALL retain the identifier returned when it records an illegal-action
finding. It SHALL direct the owning seat to perform that finding's concrete undo, verify the undo
against game state, and resolve that exact identifier before the seat receives another normal-play
prompt. The skill SHALL require later prompts to contain only findings still open for their target
seat and SHALL forbid repeating a resolved finding as an active constraint. A recovery-only
invocation SHALL neither grant nor consume a player turn; when recovery follows a completed turn
report, the current seat loop SHALL continue with the next seat rather than replaying that turn.

#### Scenario: An undo is verified and closed
- **WHEN** a seat reports that it performed an undo for a finding
- **THEN** the skill SHALL require the orchestrator to verify the undo in game state and resolve the
identifier returned for that finding before scheduling the seat's next normal turn

#### Scenario: Recovery after a completed turn does not replay the turn
- **WHEN** a finding is raised from a seat's completed turn report and the seat completes recovery
- **THEN** the orchestrator SHALL continue the current seat loop with the next seat
- **AND** SHALL not send the recovered seat another ordinary turn prompt in that round

#### Scenario: A resolved finding is absent from a later prompt
- **WHEN** the orchestrator has resolved a finding identifier
- **THEN** the skill SHALL require the next normal-play prompt for that seat to omit that finding

### Requirement: The orchestrator skill gates phase progression on encounter resolution

The orchestrator skill SHALL require every encounter card dealt during the villain phase to be
revealed and resolved in the prescribed player order before it advances the phase. It SHALL require
a verified state checkpoint after the encounter queue is resolved and SHALL abort rather than
progress when facedown encounter cards or their required effects remain unexplained.

#### Scenario: Encounter cards are resolved before the phase ends
- **WHEN** the villain phase deals one or more encounter cards
- **THEN** the skill SHALL require the orchestrator to reveal and resolve each card before advancing
  the phase

#### Scenario: Encounter state remains unresolved
- **WHEN** the post-encounter checkpoint shows unexplained facedown encounter cards or unresolved
  required effects
- **THEN** the skill SHALL require the orchestrator to abort the game and report the unresolved
  encounter state
