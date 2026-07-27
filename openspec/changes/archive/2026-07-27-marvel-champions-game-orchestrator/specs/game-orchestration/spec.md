## ADDED Requirements

### Requirement: Orchestrator skill for cooperative Marvel Champions games
The system SHALL provide a `marvel-champions-orchestrator` skill that instructs an agent session how to run a complete cooperative Marvel Champions game with one agent per player seat. The skill SHALL be discoverable by name through the skill catalogue and assignable to a session like any other skill.

#### Scenario: Skill is discoverable and loadable
- **WHEN** a client lists the available skills
- **THEN** `marvel-champions-orchestrator` SHALL appear with a description identifying it as the multi-player game orchestrator
- **AND** an agent whose session has the skill enabled SHALL be able to load its content with `load_skill`

#### Scenario: Skill exposes its references
- **WHEN** the orchestrator agent loads the skill
- **THEN** the returned content SHALL list the skill's reference files
- **AND** each listed reference SHALL be loadable with `load_skill_reference`

### Requirement: Separation of orchestrator and player authority
The orchestrator SHALL coordinate the game and SHALL NOT make a hero's play decisions. Each player agent SHALL decide and execute only its own hero's actions and SHALL NOT advance phases, resolve the villain phase, or act for another seat. This separation SHALL hold for every round so that each player agent's recorded moves reflect only that player's own decisions.

#### Scenario: Orchestrator defers a hero decision to its seat
- **WHEN** it is a seat's turn during the player phase
- **THEN** the orchestrator SHALL prompt that seat's player agent and SHALL NOT choose which cards that hero plays

#### Scenario: Player agent stays within its seat
- **WHEN** a player agent takes its turn
- **THEN** the skill SHALL instruct it to act only on its own hero and its own cards, and to end its turn by reporting back rather than by advancing the game phase

### Requirement: Orchestrated round structure matches the game rules
The orchestrator SHALL drive each round in the order defined by the Marvel Champions rules: the player phase in which every seat takes a turn in player order, the end of the player phase, the villain phase, passing the first player marker, and then the next round. The orchestrator SHALL perform the villain phase and the phase transitions itself through game-service tools rather than delegating them to a player agent.

#### Scenario: Player phase prompts every seat in player order
- **WHEN** a round's player phase begins
- **THEN** the orchestrator SHALL prompt each seat's player agent in player order starting from the current first player
- **AND** SHALL wait for a seat to report its turn complete before prompting the next seat

#### Scenario: Villain phase is run by the orchestrator
- **WHEN** every seat has completed its turn and the player phase has ended
- **THEN** the orchestrator SHALL resolve the villain phase through game-service tools, including villain and minion activations against each player and the dealing and revealing of encounter cards

#### Scenario: First player marker passes each round
- **WHEN** the villain phase completes
- **THEN** the orchestrator SHALL pass the first player marker to the next player before beginning the following round

### Requirement: Orchestrator detects and reports game end
The orchestrator SHALL check for the game's win and loss conditions each round and SHALL stop the round loop and report the outcome when one is met.

#### Scenario: Players win
- **WHEN** the final villain stage has no hit points remaining
- **THEN** the orchestrator SHALL stop prompting players and SHALL report that the players won, together with the round number reached

#### Scenario: Villain wins
- **WHEN** threat on the final main scheme reaches its target, or every player has been defeated
- **THEN** the orchestrator SHALL stop prompting players and SHALL report that the villain won, together with the round number reached

### Requirement: Comparable per-seat play
Because each seat is played by an independently configured agent whose moves are attributed to that seat on the recorded timeline, the system SHALL make it possible to evaluate and compare two configurations that played the same game.

#### Scenario: Two configurations play one game
- **WHEN** an orchestrator session is configured with two player agents that differ in model, reasoning effort, or skills
- **THEN** each seat's moves SHALL be recorded against that seat
- **AND** an evaluation of that game SHALL be able to produce a separate result per seat
