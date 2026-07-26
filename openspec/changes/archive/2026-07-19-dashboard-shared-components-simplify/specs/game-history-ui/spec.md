## MODIFIED Requirements

### Requirement: Readable conversation rendering

The dashboard history transcript SHALL render an agent move's captured conversation context — user/assistant/system messages, reasoning, and tool calls with their results — inline in the transcript event (not via a separate detail component), using the same transcript presentation as the Play tab, rather than raw JSON. The collapsible detail card used for this presentation SHALL be a single shared component reused by both the Play tab and the History transcript, with no change to its rendered output or `data-testid` values.

#### Scenario: Agent move shows a readable transcript

- WHEN the user selects an `agent_move` event whose payload carries a conversation context
- THEN the detail renders the messages, reasoning, and tool calls/results as a readable transcript (matching the Play tab's presentation), not as raw JSON

#### Scenario: Tool-call card expands to reveal its body

- WHEN the user clicks a collapsed tool-call or system-prompt card in the transcript
- THEN the card expands to show its body, using the same shared collapsible card the Play tab renders
