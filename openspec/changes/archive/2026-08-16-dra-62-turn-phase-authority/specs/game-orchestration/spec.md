## MODIFIED Requirements

### Requirement: Separation of orchestrator and player authority
The orchestrator SHALL coordinate the game and SHALL NOT make a hero's play decisions. Each player agent SHALL decide and execute only its own hero's actions and SHALL NOT advance phases, resolve the villain phase, or act for another seat. This separation SHALL hold for every round so that each player agent's recorded moves reflect only that player's own decisions.

In an orchestrated session the card-ownership half of this separation SHALL be enforced by the server and SHALL NOT rest on the skill's instructions: a tool call from a seat that identifies another seat's cards SHALL be refused before the tool is invoked, whether the seat was instructed to make it, persuaded into it, or chose it. The instructions in the skill SHALL remain, because an agent that understands its scope plays better than one that discovers it through errors — but they are guidance layered over enforcement, not the enforcement itself.

The turn-and-phase half of the separation SHALL also be enforced by the server, after the fact: when a seat's tool call is a phase-advancing tool (`next_step`, `prev_step`, `player_end_phase`, `villain_end_phase`) or a seat action tool, the runtime SHALL read the current phase from game state and, when the board is outside the player phase (villain phase, beginning of round, or end of round), SHALL record an illegal-action finding against that seat through the same findings store the `report_illegal_action` tool writes to. The call SHALL NOT be refused — detection is after the fact — and the finding SHALL be carried into every later invocation of that seat until the orchestrator resolves it, and SHALL reach the durable timeline as an `illegal_action` history event. The state read SHALL happen only for those phase-sensitive game-service tools, SHALL use the same game-service state read the session already holds, and SHALL degrade to no finding rather than failing the job when the state cannot be read. The acting player within the player phase is not a field in game state, so turn order within the player phase SHALL remain the orchestrator's prompt-tracked responsibility.

#### Scenario: Orchestrator defers a hero decision to its seat
- **WHEN** it is a seat's turn during the player phase
- **THEN** the orchestrator SHALL prompt that seat's player agent and SHALL NOT choose which cards that hero plays

#### Scenario: Player agent stays within its seat
- **WHEN** a player agent takes its turn
- **THEN** the skill SHALL instruct it to act only on its own hero and its own cards, and to end its turn by reporting back rather than by advancing the game phase

#### Scenario: A seat reaching for another seat's cards is refused, not merely discouraged
- **WHEN** a player agent in an orchestrated session calls a tool identifying another seat's cards
- **THEN** the call SHALL be refused before the tool is invoked and the attempt SHALL be recorded on the seat's job

#### Scenario: A seat advancing the phase outside the player phase gets a finding
- **WHEN** a player agent in an orchestrated session calls a phase-advancing tool while the board is outside the player phase
- **THEN** the call SHALL still be dispatched
- **AND** an open illegal-action finding SHALL be recorded against that seat, carried into its later invocations and emitted as an `illegal_action` history event

#### Scenario: A seat playing an action tool during the villain phase gets a finding
- **WHEN** a player agent in an orchestrated session calls a seat action tool while the villain phase resolves
- **THEN** the call SHALL still be dispatched
- **AND** an open illegal-action finding SHALL be recorded against that seat

#### Scenario: A seat acting during the player phase records no finding
- **WHEN** a player agent in an orchestrated session calls an action tool or a phase-advancing tool while the board is in the player phase
- **THEN** no finding SHALL be recorded for that call

#### Scenario: A read-only or setup tool never records a finding
- **WHEN** a player agent calls a read-only tool (`get_game_state`, card search), a lifecycle tool (`create_game`, deck loading, `set_player_count_action`) or `mulligan_draw_hand` at any step
- **THEN** no finding SHALL be recorded for that call
