## MODIFIED Requirements

### Requirement: Readable conversation rendering

The dashboard history transcript SHALL render an agent move's captured conversation context — user/assistant/system messages, reasoning, and tool calls with their results — inline in the transcript event (not via a separate detail component), using the same transcript presentation as the Play tab, rather than raw JSON.

#### Scenario: Agent move shows a readable transcript

- WHEN the user selects an `agent_move` event whose payload carries a conversation context
- THEN the detail renders the messages, reasoning, and tool calls/results as a readable transcript (matching the Play tab's presentation), not as raw JSON
