## ADDED Requirements

### Requirement: The user chooses a session's mode when creating it
The session configuration surface SHALL offer a control that chooses between the chat mode and the orchestrated mode, and the chosen value SHALL be sent when the session is created and when its configuration is saved. The control SHALL be a new component and SHALL NOT restyle any existing control on that surface.

The chat mode SHALL be the value a fresh draft carries, so a user who never touches the control creates the session they create today. The control SHALL state what each mode means in one line each, because the difference between one agent and one agent per seat is not conveyed by the words alone.

On a session that has already run a job the control SHALL be disabled and SHALL say why, matching the server's refusal to change the mode of a session that has started.

A stored draft from before this control existed SHALL still load, defaulting to the chat mode rather than being discarded.

#### Scenario: A fresh draft is in chat mode
- **WHEN** the configuration surface is opened with a fresh draft
- **THEN** the mode control SHALL show the chat mode as selected

#### Scenario: Choosing orchestrated mode is sent on create
- **WHEN** the user selects the orchestrated mode and creates a session
- **THEN** the create request SHALL name the orchestrated mode

#### Scenario: The control is inert on a started session
- **WHEN** the selected session has already run a job
- **THEN** the mode control SHALL be disabled and SHALL explain that a started session's mode cannot change

#### Scenario: An older stored draft still loads
- **WHEN** a stored draft that predates the mode control is loaded
- **THEN** it SHALL load successfully with the chat mode selected

### Requirement: An orchestrated session shows its seats and each seat's configuration
For a session in orchestrated mode, the dashboard SHALL show the configured seats as a roster, and for each seat SHALL show its seat identifier, its display name if it has one, its persona if it names one, and the model it will run with. This is the surface on which a user gives two seats different personas and different models, so the persona and the model SHALL be editable per seat.

For a session in chat mode the roster SHALL NOT be shown, because a chat session has no seats.

#### Scenario: The roster lists each configured seat
- **WHEN** an orchestrated session with two configured seats is selected
- **THEN** the dashboard SHALL show both seats with their identifiers, personas, and models

#### Scenario: The roster is absent in chat mode
- **WHEN** a session in chat mode is selected
- **THEN** no seat roster SHALL be shown

### Requirement: The user can read each player's own context
For each seat of an orchestrated session that has been prompted at least once, the dashboard SHALL offer a way to open that seat's own transcript, showing what that player agent was told, what it reasoned, which tools it called, and what it reported. A seat's context SHALL be presented through the existing session transcript rather than through a separate viewer, because a seat is a session.

A seat that has never been prompted SHALL show that it has no context yet rather than offering an empty transcript.

#### Scenario: Opening a seat's context
- **WHEN** the user selects a seat that has been prompted
- **THEN** the dashboard SHALL show that seat's session transcript

#### Scenario: A seat that has not played yet
- **WHEN** the user selects a seat that has never been prompted
- **THEN** the dashboard SHALL say the seat has no context yet

### Requirement: Seat-scope refusals and illegal-action findings are visible in the transcript
The transcript SHALL render the event recorded when a seat's tool call was refused for naming another seat's cards, and SHALL render it as a refusal rather than as an ordinary tool call, so a user reading a game can see that the boundary held.

The transcript SHALL render an illegal-action finding recorded against a seat, naming the seat, what was violated, and whether the finding is still open.

All text on these surfaces originates from a model or from the server and SHALL be rendered as plain text, never as markup and never interpolated anywhere it would be resolved as a reference.

#### Scenario: A refused call is shown as a refusal
- **WHEN** the timeline contains a seat-scope violation event
- **THEN** the transcript SHALL render it as a refusal naming the offending argument and the foreign seat

#### Scenario: An open finding is shown as open
- **WHEN** the timeline contains an illegal-action finding that has not been resolved
- **THEN** the transcript SHALL show it as open, naming the seat and the violation
