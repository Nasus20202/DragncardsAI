## ADDED Requirements

### Requirement: A session records the mode it runs in
Every session SHALL carry a mode that is either `chat` or `orchestrated`, stored as a first-class session property rather than as free-form metadata, so that it is queryable, has a default for rows created before the mode existed, and cannot be changed through the metadata blob a client may write freely.

The mode SHALL default to `chat`. A session created without naming a mode, and every session that existed before the mode was introduced, SHALL be `chat` and SHALL behave exactly as sessions behaved before this capability existed. The session-creation and session-update endpoints SHALL accept the mode, and every session response SHALL report it.

A session's mode SHALL be changeable only while the session has never run a job. Once a job has been created for the session the mode SHALL be frozen, and an attempt to change it SHALL be refused as a conflict. This is because an orchestrated session's seats own persistent child sessions recorded against them: leaving orchestrated mode would abandon those sessions, and entering it would begin applying seat scoping to a conversation whose agent holds no seat.

A mode value other than `chat` or `orchestrated` SHALL be rejected as a bad request.

#### Scenario: A session defaults to chat mode
- **WHEN** a client creates a session without naming a mode
- **THEN** the created session SHALL report mode `chat`

#### Scenario: A session is created in orchestrated mode
- **WHEN** a client creates a session naming mode `orchestrated`
- **THEN** the created session SHALL report mode `orchestrated`

#### Scenario: The mode is changeable before the first job
- **WHEN** a client updates the mode of a session that has never run a job
- **THEN** the update SHALL be applied and the session SHALL report the new mode

#### Scenario: The mode is frozen after the first job
- **WHEN** a client updates the mode of a session that has at least one job
- **THEN** the request SHALL be refused as a conflict and the stored mode SHALL be unchanged

#### Scenario: An unknown mode is rejected
- **WHEN** a client creates or updates a session naming a mode that is neither `chat` nor `orchestrated`
- **THEN** the request SHALL be rejected as a bad request

### Requirement: A player seat owns a persistent agent session
In an orchestrated session, each configured seat SHALL own its own agent session that persists across invocations, so that a seat prompted in one round retains what it did, drew, discarded, and agreed with other seats when it is prompted in a later round.

The first time a seat is prompted, the system SHALL create that session with multi-turn memory enabled, materialise onto it the seat's resolved provider, model, options, and skills, materialise the seat's persona snapshot if the seat names a persona, tag it with the seat id and the orchestrating session id, and record the created session's identifier on the seat's stored configuration. Every later prompt for the same seat SHALL enqueue a job on that same recorded session rather than creating a new one, so the seat's own prior turns are replayed into its next invocation by the ordinary conversation-history mechanism.

A seat's session SHALL NOT be terminated when one of its jobs ends. It SHALL be terminated when the orchestrating session is terminated and when the seat's configuration is deleted, so a finished game leaves no running session behind.

A seat's persona SHALL be captured when the seat's session is created and SHALL NOT be re-read afterwards, so editing or deleting a persona mid-game never changes a seat that is already playing.

The seat identifier SHALL be exposed through the players API together with the seat's session identifier, so a client can read a seat's context by reading that session.

In a `chat` session, prompting a player agent SHALL keep the pre-existing behaviour of creating a memoryless child session that is terminated when its job ends.

#### Scenario: The first prompt creates the seat's session
- **WHEN** a seat with no recorded session is prompted in an orchestrated session
- **THEN** the system SHALL create a session with multi-turn memory enabled and SHALL record its identifier on the seat

#### Scenario: A later prompt reuses the seat's session
- **WHEN** a seat that already has a recorded session is prompted again
- **THEN** the system SHALL enqueue the job on the recorded session and SHALL NOT create another session

#### Scenario: The seat remembers its earlier turn
- **WHEN** a seat is prompted a second time
- **THEN** the messages sent to the model SHALL include the seat's own earlier turn

#### Scenario: A seat's session survives its job
- **WHEN** a seat's job reaches a terminal status
- **THEN** the seat's session SHALL remain active

#### Scenario: Deleting a seat terminates its session
- **WHEN** a seat's configuration is deleted
- **THEN** the session recorded on that seat SHALL be terminated

#### Scenario: A chat session's player agent stays memoryless
- **WHEN** a player agent is prompted from a session whose mode is `chat`
- **THEN** the child session SHALL be created without multi-turn memory and SHALL be terminated when its job ends

### Requirement: A seat may act only on its own cards, enforced by the server
A tool call made by a player-seat job SHALL be checked against the caller's own seat before it is dispatched, and SHALL be refused when any argument identifies a player seat other than the caller's own. Refusal SHALL mean the tool is not invoked at all.

The caller's seat SHALL be determined from the seat identity recorded on its session by the orchestrator, and SHALL NOT be taken from anything the player agent can write. A player agent SHALL have no way to change the seat it is treated as.

The check SHALL recognise the ways card ownership is addressed: an argument that is or contains a seat identifier, an argument that names a player-owned group belonging to another seat, and an explicit player-identifying argument. Groups that are not owned by a seat SHALL NOT be restricted, because a seat legitimately affects the villain and shared areas during its own turn.

A refused call SHALL return an error result naming which argument identified which foreign seat, so the agent can correct itself, and SHALL be recorded as an event on the job so the attempt is visible in the session's timeline and to evaluation.

Enforcement SHALL NOT depend on the seat's instructions. A seat that is told, tricked, or decides to act for another seat SHALL be refused identically.

#### Scenario: A seat acting on another seat's group is refused
- **WHEN** a player agent for seat `player1` calls a tool naming a group owned by seat `player2`
- **THEN** the tool SHALL NOT be invoked, an error result SHALL name the offending argument and the foreign seat, and a seat-scope-violation event SHALL be recorded on the job

#### Scenario: A seat acting on its own group is allowed
- **WHEN** a player agent for seat `player1` calls a tool naming a group owned by seat `player1`
- **THEN** the tool SHALL be invoked normally

#### Scenario: A seat affecting a shared area is allowed
- **WHEN** a player agent calls a tool naming a group that no seat owns
- **THEN** the tool SHALL be invoked normally

#### Scenario: An explicit foreign seat argument is refused
- **WHEN** a player agent for seat `player1` calls a tool with a player-identifying argument whose value is `player3`
- **THEN** the tool SHALL NOT be invoked and an error result SHALL be returned

#### Scenario: The orchestrator is not seat-scoped
- **WHEN** the orchestrating job calls a tool naming any group
- **THEN** the seat check SHALL NOT apply, because the orchestrator holds no seat

### Requirement: A player's output reaches the orchestrator as data, never as instruction
Text authored by a player agent SHALL NOT enter the orchestrator's system prompt. The orchestrator's system prompt SHALL be assembled only from the system's own static text, the on-disk skill registry, and the persona catalogue's names, display names, and descriptions. No parameter or code path SHALL carry player-authored text into it.

A seat's outcome SHALL reach the orchestrator only as an ordinary tool result carrying a structured report envelope. The envelope SHALL state the seat identifier and the job status as fields the server sets, and SHALL confine the seat's own text to a single delimited block introduced as untrusted seat output that reports observations and carries no authority over the rules, the phase order, or what is legal.

The seat identifier in the envelope SHALL be taken from the seat identity recorded on the seat's session, so a seat cannot present itself as another seat by writing one into its prose.

The delimiters bounding the seat's text SHALL be removed from that text before it is wrapped, so a seat cannot close the block early and have the remainder of its output read as if it came from outside the block.

A player agent SHALL have no tool that sends anything to the orchestrator. One report per invocation, produced by the run's completion, SHALL be the whole of the player-to-orchestrator channel.

#### Scenario: Player text is absent from the orchestrator's system prompt
- **WHEN** a seat's report contains text attempting to override instructions
- **THEN** that text SHALL NOT appear anywhere in the orchestrator's assembled system prompt

#### Scenario: A report is wrapped as labelled data
- **WHEN** a seat's report is delivered to the orchestrator
- **THEN** it SHALL arrive as a tool result whose envelope names the seat and the job status as fields and confines the seat's text to a delimited block labelled as untrusted data

#### Scenario: A seat cannot forge another seat's identity
- **WHEN** a seat's report text claims to be from a different seat
- **THEN** the envelope's seat field SHALL still name the seat whose session produced the report

#### Scenario: A seat cannot escape its own block
- **WHEN** a seat's report text contains the closing delimiter
- **THEN** the delimiter SHALL be removed from the text and the wrapped block SHALL still be closed exactly once by the server

### Requirement: Legality is decided from game state, never from a player's assertion
Whether a move was legal SHALL be decided from the game's own validation and from game state read through the deciding party's own tools. A player's assertion — that a move was legal, that a rule does not apply, that permission was granted, or that a violation was already corrected — SHALL NOT be an input to the decision.

A player-supplied claim SHALL be treated as part of that player's report, which is data. No code path SHALL allow a player-supplied value to stand in for a legality check, and no optimisation SHALL skip reading game state on the strength of a seat's self-report.

#### Scenario: A player's claim does not make a move legal
- **WHEN** a seat reports that a move it made was permitted
- **THEN** the legality decision SHALL still be taken from game state and the report SHALL carry no weight of its own

#### Scenario: A claimed revert is verified
- **WHEN** a seat reports that it has undone an illegal action
- **THEN** the finding SHALL remain open until the undo is confirmed against game state

### Requirement: Player agents can message each other and cannot message the orchestrator
The system SHALL offer a message-sending tool to player-seat jobs of an orchestrated session, and SHALL NOT offer it to an orchestrating job or to any job of a `chat` session.

A message SHALL be addressed to a seat identifier. The recipient SHALL be a configured seat of the same orchestrating session; a recipient that is not a configured seat, that belongs to another orchestrating session, or that names the sender itself SHALL be refused with an error result. There SHALL be no recipient value that reaches the orchestrator.

Messages SHALL be stored durably with their sender, recipient, orchestrating session, body, and delivery state. They SHALL NOT be held in process memory, because the sending seat and the receiving seat run as separate jobs that may run on separate replicas and at different times.

Messages addressed to a seat and not yet delivered SHALL be delivered at the start of that seat's next invocation, wrapped as data attributed to the sending seat and framed as untrusted seat output exactly as a player report is, and SHALL then be marked delivered so they are not delivered twice.

#### Scenario: A seat messages another seat
- **WHEN** the player agent for seat `player1` sends a message to seat `player2`
- **THEN** the message SHALL be stored against the orchestrating session with sender `player1` and recipient `player2`

#### Scenario: The tool is not offered to the orchestrator
- **WHEN** the effective tool list is built for an orchestrating job
- **THEN** the message-sending tool SHALL NOT appear in it

#### Scenario: The tool is not offered in chat mode
- **WHEN** the effective tool list is built for any job of a session whose mode is `chat`
- **THEN** the message-sending tool SHALL NOT appear in it

#### Scenario: An unconfigured recipient is refused
- **WHEN** a seat sends a message to a seat identifier that is not configured on the orchestrating session
- **THEN** an error result SHALL be returned and nothing SHALL be stored

#### Scenario: Pending messages are delivered once
- **WHEN** a seat with two undelivered messages is prompted
- **THEN** both messages SHALL be included in that invocation as data attributed to their senders
- **AND** a subsequent invocation SHALL NOT include them again

### Requirement: Illegal actions are recorded, carried to the seat, and resolved only by verification
The system SHALL durably record findings that a seat's action violated the rules. A finding SHALL carry the orchestrating session, the seat, what was violated, what must be undone, its status, and the note recorded when it was resolved.

Only the orchestrating job SHALL be able to open a finding and to resolve one. A player-seat job SHALL be able to read the findings addressed to its own seat and SHALL NOT be able to resolve one, because resolution is a judgement about game state and belongs to the party that reads game state authoritatively.

An open finding SHALL be included in every subsequent invocation of the seat it concerns, as data naming what was violated and what must be undone, until it is resolved. A seat SHALL NOT be able to outlast a finding by ignoring one invocation.

#### Scenario: The orchestrator opens a finding
- **WHEN** the orchestrating job records that seat `player2` made an illegal move
- **THEN** an open finding SHALL be stored against that seat

#### Scenario: An open finding follows the seat
- **WHEN** a seat with an open finding is prompted
- **THEN** the invocation SHALL include the finding as data naming the violation and the required undo

#### Scenario: A seat cannot resolve its own finding
- **WHEN** a player-seat job attempts to resolve a finding
- **THEN** the attempt SHALL be refused and the finding SHALL remain open

#### Scenario: A resolved finding stops following the seat
- **WHEN** the orchestrating job resolves a finding after verifying the undo against game state
- **THEN** later invocations of that seat SHALL NOT include it

### Requirement: A seat's configuration names its persona
A seat's stored configuration SHALL be able to name a persona, in addition to the provider, model, options, and skills it can already name, so two seats at the same table can differ in character as well as in model.

A named persona SHALL be resolved when the seat's session is created, and SHALL be applied under the same rules that apply to any persona: it may narrow the seat's tool access and SHALL NOT widen it, and its prompt SHALL be treated as user-authored text that is never used as a format string and never grants capability.

A seat naming a persona that does not exist SHALL be rejected when the seat is configured, so the failure is reported to the user configuring the table rather than to the orchestrator mid-game.

#### Scenario: A seat is configured with a persona
- **WHEN** a client configures seat `player1` naming an existing persona
- **THEN** the seat's stored configuration SHALL record that persona and the players API SHALL report it

#### Scenario: An unknown persona is rejected at configuration time
- **WHEN** a client configures a seat naming a persona that does not exist
- **THEN** the request SHALL be rejected as a bad request

#### Scenario: Two seats can hold different personas and models
- **WHEN** two seats are configured with different personas and different models
- **THEN** each seat's session SHALL be created with its own persona snapshot and its own model configuration
