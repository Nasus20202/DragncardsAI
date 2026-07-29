## ADDED Requirements

### Requirement: A question from the agent is answered by clicking
When a job's event timeline carries a question from the agent, the transcript SHALL render it as its own surface showing the question and one clickable control per offered choice, rather than as a generic tool-call block. Activating a control SHALL submit that choice as the answer without the user typing anything.

When the question permits a free-text answer, the surface SHALL additionally offer a text field and a way to submit it. When it does not, no text field SHALL be offered, so the surface never invites an answer the orchestrator will refuse.

While an answer is being submitted, every control on the surface SHALL be disabled, so one user cannot submit two answers by clicking twice.

The surface SHALL be a new component and SHALL follow the transcript's existing visual language. No existing transcript, composer, or tool-call rendering SHALL be restyled by this change.

#### Scenario: Clicking a choice answers the question
- **WHEN** the transcript shows a question awaiting an answer with two offered choices
- **THEN** it SHALL render one control per choice
- **AND WHEN** the user activates one
- **THEN** the dashboard SHALL submit that choice's value as the answer for that question

#### Scenario: Free text is offered only when permitted
- **WHEN** a question that does not permit free text is awaiting an answer
- **THEN** the surface SHALL NOT offer a text field

#### Scenario: Controls are disabled while submitting
- **WHEN** the user has activated a choice and the submission has not yet resolved
- **THEN** every control on the surface SHALL be disabled

### Requirement: A question's state survives a reload
The dashboard SHALL derive each question's state from the job's persisted event timeline, which it already replays on load and on reconnect, and SHALL NOT hold pending-question state anywhere else. Reloading the page or losing and re-establishing the event stream SHALL therefore restore what the user was looking at.

A question that is still awaiting an answer SHALL come back with its controls live. A question that has been answered SHALL come back showing the answer that was recorded, with no controls, because answering again is impossible. A question that was closed without an answer SHALL come back saying so, distinguishing a question nobody answered in time from one ended by cancellation.

The events that resolve a question SHALL resolve the question's own surface rather than appearing as separate entries in the transcript, so a question and its answer read as one exchange.

#### Scenario: An answered question comes back answered
- **WHEN** a job's replayed timeline contains a question followed by its answer
- **THEN** the transcript SHALL show the recorded answer and SHALL NOT render any answering controls

#### Scenario: A closed question comes back closed
- **WHEN** a job's replayed timeline contains a question followed by its closure
- **THEN** the transcript SHALL say the question is no longer awaiting an answer, naming whether it timed out or was cancelled, and SHALL NOT render any answering controls

#### Scenario: An answer is not a separate transcript entry
- **WHEN** a job's replayed timeline contains a question and its answer
- **THEN** the answer SHALL be shown on the question's own surface and SHALL NOT appear as an additional transcript entry

### Requirement: A question that can no longer be answered offers no controls
When the job that asked a question has reached a terminal status while the question is still awaiting an answer, the surface SHALL disable its controls and explain that the question can no longer be answered. This is the case where the run that was waiting is gone, and offering a control that the orchestrator will refuse would be misleading.

When a submission is refused because the question is no longer awaiting an answer, the surface SHALL show the reason the orchestrator gave and SHALL leave its controls disabled rather than inviting a retry.

#### Scenario: A finished job's pending question is inert
- **WHEN** a question is still awaiting an answer but its job has reached a terminal status
- **THEN** the surface SHALL disable its controls and SHALL explain that the question can no longer be answered

#### Scenario: A refused answer is explained, not retried
- **WHEN** submitting an answer is refused because the question is no longer awaiting one
- **THEN** the surface SHALL show the reason given and SHALL leave its controls disabled

### Requirement: Model-authored question text is rendered as text
The question text and each choice's label, value, and description are authored by the model. The dashboard SHALL render them as plain text only. It SHALL NOT render them as markup or markdown, and SHALL NOT interpolate them into an attribute, a style, or anything else that is executed or resolved as a reference.

#### Scenario: Markup in a choice label stays literal
- **WHEN** a choice label contains characters that would form an HTML element
- **THEN** the transcript SHALL display those characters as text
- **AND** no element described by that text SHALL exist in the rendered output
