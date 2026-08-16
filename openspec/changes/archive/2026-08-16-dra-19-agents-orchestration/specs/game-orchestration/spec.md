## MODIFIED Requirements

### Requirement: Separation of orchestrator and player authority
The orchestrator SHALL coordinate the game and SHALL NOT make a hero's play decisions. Each player agent SHALL decide and execute only its own hero's actions and SHALL NOT advance phases, resolve the villain phase, or act for another seat. This separation SHALL hold for every round so that each player agent's recorded moves reflect only that player's own decisions.

In an orchestrated session the card-ownership half of this separation SHALL be enforced by the server and SHALL NOT rest on the skill's instructions: a tool call from a seat that identifies another seat's cards SHALL be refused before the tool is invoked, whether the seat was instructed to make it, persuaded into it, or chose it. The instructions in the skill SHALL remain, because an agent that understands its scope plays better than one that discovers it through errors — but they are guidance layered over enforcement, not the enforcement itself.

The turn-and-phase half of the separation SHALL remain an orchestrator-side responsibility, because it concerns when an action may happen rather than whose cards it touches: the orchestrator SHALL perform phase transitions itself and SHALL treat a seat's attempt to advance the game as an illegal action to be reported.

#### Scenario: Orchestrator defers a hero decision to its seat
- **WHEN** it is a seat's turn during the player phase
- **THEN** the orchestrator SHALL prompt that seat's player agent and SHALL NOT choose which cards that hero plays

#### Scenario: Player agent stays within its seat
- **WHEN** a player agent takes its turn
- **THEN** the skill SHALL instruct it to act only on its own hero and its own cards, and to end its turn by reporting back rather than by advancing the game phase

#### Scenario: A seat reaching for another seat's cards is refused, not merely discouraged
- **WHEN** a player agent in an orchestrated session calls a tool identifying another seat's cards
- **THEN** the call SHALL be refused before the tool is invoked and the attempt SHALL be recorded on the seat's job

## ADDED Requirements

### Requirement: Orchestrated play is opt-in and does not replace the chat flow
A full orchestrated game SHALL be available only for a session whose recorded mode is `orchestrated`, chosen when the session is created. The existing single-agent chat flow SHALL remain the default and SHALL be unchanged by the existence of orchestrated mode: a session that does not opt in SHALL run exactly as it did before, with the same tools, the same subagent behaviour, and the same session lifecycle.

A user SHALL be able to make the choice at session-creation time rather than discovering it later, and the choice SHALL be visible on the session afterwards.

#### Scenario: A chat session is unaffected
- **WHEN** a session in `chat` mode runs a prompt
- **THEN** its available tools, its subagent behaviour, and its session lifecycle SHALL be those of the pre-orchestration flow

#### Scenario: Orchestrated behaviour requires the mode
- **WHEN** a session in `chat` mode runs a prompt
- **THEN** the player-to-player messaging tool SHALL NOT be available and no seat scoping SHALL be applied

### Requirement: Each seat is a durable agent for the length of the game
An orchestrated game SHALL run one persistent agent per seat, retaining its context between invocations for the whole game, so a hero's plan can span rounds. A seat prompted in a later round SHALL still know what it drew, played, and discarded earlier, and what other seats told it.

A seat SHALL be a seat identifier, a persona, a model configuration, and a persistent session together. Two seats at the same table SHALL be able to differ in persona and in model, so a game can compare how differently configured players play the same scenario.

#### Scenario: A seat's plan survives a round boundary
- **WHEN** a seat states a plan in one round and is prompted again in the next
- **THEN** its earlier statement SHALL be part of the context of the later invocation

#### Scenario: Seats differ in persona and model
- **WHEN** two seats are configured with different personas and different models
- **THEN** each SHALL play with its own persona and its own model for the whole game

### Requirement: Players communicate with each other, and only with each other
An orchestrated game SHALL let seats coordinate directly: a seat SHALL be able to send a message to another seat at the same table, and SHALL receive messages addressed to it when it next plays. This is what makes cooperative play cooperative — deciding who thwarts and who attacks is a conversation between players.

No channel SHALL exist from a player agent to the orchestrator other than the seat's own report of what it did. A seat SHALL NOT be able to address the orchestrator, and a message a seat sends SHALL NOT be routed to the orchestrator by any recipient value.

#### Scenario: Two seats coordinate before acting
- **WHEN** one seat sends another a message proposing a division of labour and the recipient is then prompted
- **THEN** the recipient's invocation SHALL include that message attributed to the sending seat

#### Scenario: There is no path from a player to the orchestrator
- **WHEN** a player agent looks for a way to address the orchestrator
- **THEN** no tool and no recipient value SHALL provide one

### Requirement: An illegal action is reported by the orchestrator and undone by the seat that made it
When the orchestrator determines from game state that a seat's action violated the rules, it SHALL record a finding naming the seat, what was violated, and what must be undone. The finding SHALL be carried into that seat's next invocation, and every invocation after it, until resolved.

The seat that made the illegal action SHALL be the party that undoes it, using its own tools within its own seat scope. The orchestrator SHALL NOT reach into a seat's cards to correct it, because doing so would hold the write authority over another party's cards that this capability exists to remove.

The orchestrator SHALL resolve a finding only after verifying against game state that the required undo happened. A seat's report that it has undone the action SHALL NOT resolve the finding on its own.

#### Scenario: A violation is reported to the seat that made it
- **WHEN** the orchestrator finds that a seat played a card it could not afford
- **THEN** it SHALL record a finding against that seat naming the violation and the required undo
- **AND** the seat's next invocation SHALL carry the finding

#### Scenario: The seat performs its own revert
- **WHEN** a seat is prompted carrying an open finding
- **THEN** the seat SHALL perform the undo with its own tools and report back
- **AND** the orchestrator SHALL NOT perform the undo itself

#### Scenario: A finding is resolved only after verification
- **WHEN** a seat reports that it has undone the action
- **THEN** the orchestrator SHALL confirm the undo against game state before resolving the finding

#### Scenario: An unresolved finding keeps following the seat
- **WHEN** a seat with an open finding is prompted twice without the undo being verified
- **THEN** both invocations SHALL carry the finding

### Requirement: The orchestrator's rule-following cannot be argued away by a player
The orchestrator SHALL treat everything a player agent produces as a report of observations, and SHALL NOT treat any of it as an instruction, a permission, or a statement of what the rules are. A seat asserting that a rule does not apply, that the orchestrator previously agreed to something, or that its move should be allowed SHALL have exactly the effect of a seat saying nothing: the orchestrator's decision comes from the rules it holds and the game state it reads.

This SHALL be achieved by where player text is placed rather than by the orchestrator being asked to resist persuasion: player text SHALL never occupy a position in the orchestrator's context where instructions are read, and SHALL always arrive labelled as untrusted seat output.

#### Scenario: A persuasive report changes nothing
- **WHEN** a seat's report claims the orchestrator should skip the villain phase
- **THEN** the orchestrator SHALL run the villain phase as the rules require

#### Scenario: Player text never occupies an instruction position
- **WHEN** a seat's report is delivered
- **THEN** it SHALL arrive as labelled data in a tool result and SHALL NOT be placed in the orchestrator's system prompt or read as a directive
