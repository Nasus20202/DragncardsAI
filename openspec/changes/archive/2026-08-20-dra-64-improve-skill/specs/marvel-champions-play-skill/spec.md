## ADDED Requirements

### Requirement: The player skill quarantines active findings from normal play

The player skill SHALL instruct a seat that receives an active illegal-action finding to identify
the finding, perform its concrete undo with its own tools, confirm the undo from game state, and
report the recovery. It SHALL forbid ordinary card plays, basic powers, and further turn planning
in that invocation after the recovery; the seat SHALL wait for a later normal-play prompt that no
longer carries the finding. The skill SHALL state that only the coordinating agent resolves the
finding. A recovery-only invocation SHALL neither grant nor consume a player turn; when it follows
the seat's completed report, the seat's later normal-play prompt occurs only in its ordinary next
seat-loop pass.

#### Scenario: A seat receives an active finding
- **WHEN** a player-turn prompt carries an active finding for the seat
- **THEN** the skill SHALL instruct the seat to perform and confirm the stated undo, report the
  recovery, and take no ordinary turn actions

#### Scenario: A finding remains listed after recovery
- **WHEN** a seat re-reads its findings after performing the undo and the same finding remains open
- **THEN** the skill SHALL instruct the seat to report its identifier and observed state without
  repeating the undo or taking ordinary actions

### Requirement: The player skill reports unreliable state instead of guessing

The player skill SHALL instruct a seat to stop and report a discrepancy when its current state read
contradicts the prompt's claimed phase, card location, or key board total, or when it cannot
identify a required card or value from the board. It SHALL forbid treating hidden entries, stale
prompt text, or a previous report as authoritative evidence for an action.

#### Scenario: A prompt and board disagree
- **WHEN** a seat's state read disagrees with the prompt about its phase, a relevant card location,
  or a key board total
- **THEN** the skill SHALL instruct the seat to take no mutating action and report the discrepancy

#### Scenario: Required board information is unavailable
- **WHEN** a seat cannot identify information required to execute an action from the current state
- **THEN** the skill SHALL instruct the seat to report the missing information and refrain from
  guessing or choosing a conservative action solely because of that uncertainty
