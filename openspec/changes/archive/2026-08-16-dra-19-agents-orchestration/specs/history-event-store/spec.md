## ADDED Requirements

### Requirement: A recorded event states the orchestration mode it came from
An event recorded from an agent session SHALL carry the mode that session runs in, so a stored timeline states whether it was produced by a single chat agent or by an orchestrated table of per-seat agents. A consumer reading a game's history SHALL be able to tell the two apart without inferring it from the presence of seat identifiers.

An event from an orchestrated session SHALL carry the seat identifier of the agent that produced it, and an event produced by the orchestrating agent itself SHALL carry no seat identifier, so the orchestrator's own bookkeeping is distinguishable from a player's play.

An event recorded before the mode existed, and an event from a session in chat mode, SHALL read as chat mode, so the addition changes no stored meaning.

#### Scenario: An orchestrated seat's move states its mode and seat
- **WHEN** a player agent of an orchestrated session records a move
- **THEN** the stored event SHALL state the orchestrated mode and that seat's identifier

#### Scenario: The orchestrator's own event carries no seat
- **WHEN** the orchestrating agent records an event
- **THEN** the stored event SHALL state the orchestrated mode and SHALL carry no seat identifier

#### Scenario: A chat session's event reads as chat
- **WHEN** a chat session records a move
- **THEN** the stored event SHALL state the chat mode
