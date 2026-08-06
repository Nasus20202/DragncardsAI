## ADDED Requirements

### Requirement: The turn procedure states its entry conditions and refuses to guess them

The skill SHALL name the inputs a turn cannot start without — the seat identifier, the game-service session identifier, and which hero the seat controls — and SHALL instruct the agent to report the missing input and stop rather than infer it from the board. These entry conditions SHALL appear before the first ordered step of the procedure.

A player agent is prompted with no memory of previous turns, so every fact it needs arrives in the prompt or not at all. Inferring a seat is the specific failure this forbids: a board read shows every seat's zones, so a missing seat identifier looks answerable and is not.

#### Scenario: A turn prompt omits the seat

- **WHEN** the skill describes beginning a turn without a stated seat identifier
- **THEN** it SHALL instruct the agent to ask for the seat and take no mutating action
- **AND** it SHALL state that reading the board does not establish which seat the agent plays

#### Scenario: Entry conditions are listed before the first step

- **WHEN** an agent reads the turn procedure
- **THEN** the required inputs SHALL be stated before the first ordered step

### Requirement: Each step of the turn procedure states what confirms it

For each ordered step of the turn procedure the skill SHALL state the observation that confirms the step happened, SHALL state that the `error` field is read after every mutating call regardless of the reported `success` value, and SHALL instruct the agent to stop and diagnose when an observation does not match the step's intent.

A tool call that reports `success: true` may still have done nothing, so a procedure without an observation after each step cannot tell a completed step from a silently failed one.

#### Scenario: A step names its confirming observation

- **WHEN** the skill describes an ordered step that mutates the board
- **THEN** it SHALL state what the agent reads back to confirm that step took effect

#### Scenario: An unconfirmed step halts the sequence

- **WHEN** the observation after a step does not match what the step intended
- **THEN** the skill SHALL instruct the agent to stop and diagnose before issuing further actions

### Requirement: The turn procedure states its stop conditions

The skill SHALL enumerate the conditions under which a turn ends — the agent has nothing further it can pay for or usefully do, its hero is defeated, the villain stage or the main scheme reached a terminal value, or an unrecoverable error occurred — and SHALL state that in every case the turn ends by reporting and never by advancing a phase or refilling a hand. It SHALL provide a completion check answerable from the board rather than from the agent's intent.

An agent that does not know when its turn is over either keeps acting or advances the phase, and phase advancement by a seat mutates every player's board.

#### Scenario: A terminal board state ends the turn

- **WHEN** the skill describes reducing the villain stage to zero hit points or the agent's own hero being defeated
- **THEN** it SHALL instruct the agent to stop acting and report immediately, leaving stage advancement and elimination handling to the coordinator

#### Scenario: Done is defined

- **WHEN** an agent asks whether its turn is finished
- **THEN** the skill SHALL provide a stated completion check that is answerable from the board

### Requirement: The skill states what to do when a step fails and when to ask rather than guess

The skill SHALL provide an ordered failure response covering a non-null `error`, a board that does not match the agent's intent, a mistake that cannot be reversed with the agent's own tools, and the point at which the agent stops acting and reports. It SHALL also name the facts an agent must ask for rather than assume, including the main scheme's target threat, which the game state does not expose and which may be absent from the card catalogue.

#### Scenario: A failed action does not become a retry loop

- **WHEN** a mutating call returns a non-null `error`
- **THEN** the skill SHALL instruct the agent to re-read state before acting again rather than reissuing the same call

#### Scenario: An unfixable board is reported, not improvised around

- **WHEN** a mistake cannot be reversed with the tools a seat holds
- **THEN** the skill SHALL instruct the agent to state what happened, what the board shows, and what the correct board would be, and to stop

#### Scenario: An unknown value is asked for once

- **WHEN** a decision needs a value the state does not expose
- **THEN** the skill SHALL instruct the agent to ask for it and remember it rather than estimate it

### Requirement: The skill states which guardrails are enforced by the server and which are not

The skill SHALL distinguish the seat-scope refusals the server applies before a tool runs from the rules of play that nothing checks. It SHALL state that a call naming another seat's identifier, another seat's `playerN`-prefixed group, or a player-identifying argument carrying another seat's value is refused before dispatch and recorded against the job, and that a refusal is corrected by reissuing the call within the agent's own seat rather than by explanation or a claim of permission. It SHALL state that turn order, phase authority, resource cost payment, the once-per-turn form change, and the hand limit are enforced nowhere.

An agent that believes every rule is enforced treats a silent success as permission.

#### Scenario: A refusal is described as correctable

- **WHEN** the skill describes a seat-scope refusal
- **THEN** it SHALL state that the refusal names the offending argument and that the agent reissues the call with its own seat's identifiers

#### Scenario: Unenforced rules are named as the agent's own responsibility

- **WHEN** the skill describes paying a card's cost or advancing a phase
- **THEN** it SHALL state that nothing in the harness validates it and that a missed cost is cheating rather than an error

### Requirement: The skill documents the seat's view of illegal-action findings

The skill SHALL describe the illegal-action findings loop from the seat's side: that a finding recorded against the seat is presented at the start of every turn until it is closed, that the seat can list the open findings against it, that the seat performs the stated undo with its own tools before taking new actions, and that only the coordinating agent closes a finding.

#### Scenario: A seat carrying an open finding acts on it first

- **WHEN** the skill describes starting a turn while a finding is open against the agent's seat
- **THEN** it SHALL instruct the agent to perform the stated undo before taking new actions and to report that it did

#### Scenario: A seat cannot resolve its own finding

- **WHEN** the skill describes closing a finding
- **THEN** it SHALL state that only the coordinating agent resolves one, after verifying the undo against game state
