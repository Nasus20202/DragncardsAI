## MODIFIED Requirements

### Requirement: Resume a session from a supplied conversation context
The agent-orchestrator SHALL support creating or resuming an agent session seeded with a supplied conversation context and bound to a supplied restored `game_id`, so that after a history restore the agent continues from an identical decision situation.

The agent-orchestrator SHALL validate the supplied `conversation_context` before persisting it or mutating any session, because the context is replayed verbatim into the next turn's message list and sent to the LLM. The supplied `game_id` SHALL be a non-empty, length-bounded string. The `conversation_context` SHALL be rejected with a validation error when it contains more than a bounded number of messages, when any message is not an object or lacks a string `role` in the set {`system`, `user`, `assistant`, `tool`}, or when its serialized size exceeds a bounded byte limit. A well-formed context SHALL be accepted and resumed unchanged.

#### Scenario: Resume a session with a restored conversation context
- **WHEN** a restore supplies a conversation context and a restored `game_id` to the agent-orchestrator
- **THEN** the agent-orchestrator SHALL create or resume a session whose conversation context matches the supplied context and whose game binding is the restored `game_id`

#### Scenario: Resumed session can play forward
- **WHEN** a session resumed from a restored conversation context runs its next turn
- **THEN** the agent SHALL act on the restored context and game state as if continuing from the original moment

#### Scenario: Reject a malformed conversation context message
- **WHEN** a restore request supplies a `conversation_context` containing a message that is not an object or whose `role` is missing or not one of `system`, `user`, `assistant`, or `tool`
- **THEN** the agent-orchestrator SHALL reject the request with a validation error and SHALL NOT create or mutate any session

#### Scenario: Reject an oversized conversation context
- **WHEN** a restore request supplies a `conversation_context` that exceeds the bounded message count or the bounded serialized size
- **THEN** the agent-orchestrator SHALL reject the request with a validation error and SHALL NOT persist the context
