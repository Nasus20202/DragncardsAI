## ADDED Requirements

### Requirement: Dashboard application shell
The system SHALL provide a Next.js dashboard application with a dark-mode-capable HeroUI interface and top-level navigation for `Play` and `Swagger` sections.

#### Scenario: Navigate between dashboard sections
- **WHEN** a user opens the dashboard in a browser
- **THEN** the system SHALL display a top navbar with `Play` and `Swagger` navigation entries

#### Scenario: Use dark mode
- **WHEN** the user enables dark mode or the browser prefers dark mode
- **THEN** the dashboard SHALL render the application shell and main content using dark-compatible HeroUI styling

### Requirement: Play session workspace
The system SHALL provide a Play workspace that combines session history, live chat output, session configuration, and DragnCards game UI context.

#### Scenario: View play layout
- **WHEN** a user opens the Play section on a desktop viewport
- **THEN** the dashboard SHALL show session history and configuration on the left, live chat output in the center, and a collapsible DragnCards iframe panel on the right

#### Scenario: Use play layout on small screens
- **WHEN** a user opens the Play section on a narrow viewport
- **THEN** the dashboard SHALL keep chat usable and SHALL make side panels collapsible or stacked without requiring horizontal scrolling for primary chat interaction

### Requirement: Agent session management
The dashboard SHALL allow users to create, select, inspect, update, and terminate agent sessions through agent-orchestrator APIs.

#### Scenario: Create session with defaults
- **WHEN** a user creates a new Play session without changing configuration
- **THEN** the dashboard SHALL submit the configured session defaults to the agent-orchestrator and display the created session in history

#### Scenario: Inspect selected session
- **WHEN** a user selects a session from history
- **THEN** the dashboard SHALL show the session status, model/provider configuration, assigned MCPs, assigned skills, and recent job state

#### Scenario: Terminate session
- **WHEN** a user terminates an active session from the dashboard
- **THEN** the dashboard SHALL call the agent-orchestrator termination API and update the session status in the UI

### Requirement: Session configuration controls
The dashboard SHALL expose readable controls for model/provider settings, MCP assignments, skill assignments, and configurable session defaults including the default game-service MCP.

#### Scenario: Configure model and provider
- **WHEN** a user edits the model/provider configuration for a session
- **THEN** the dashboard SHALL submit the selected provider, model, and non-secret options to the agent-orchestrator

#### Scenario: Configure MCPs and skills
- **WHEN** a user edits MCP or skill assignments for a session
- **THEN** the dashboard SHALL submit the requested assignments to the agent-orchestrator and display validation errors clearly if any assignment is rejected

#### Scenario: Apply default game-service MCP
- **WHEN** session defaults include the game-service MCP
- **THEN** newly created sessions SHALL include that MCP assignment unless the user explicitly removes it before creation

### Requirement: Live chat and orchestration event rendering
The dashboard SHALL provide a ChatGPT-like prompt and transcript interface backed by agent-orchestrator prompt jobs and streaming events.

#### Scenario: Submit prompt
- **WHEN** a user submits a prompt for an active session
- **THEN** the dashboard SHALL create a prompt job through the agent-orchestrator and append the user prompt to the transcript

#### Scenario: Render streaming output
- **WHEN** the agent-orchestrator streams job events
- **THEN** the dashboard SHALL append model output chunks, progress or thinking summaries, tool calls, tool results, errors, and completion state to the transcript in arrival order or documented event order

#### Scenario: Render verbose events readably
- **WHEN** streamed events include tool calls, tool results, or progress details
- **THEN** the dashboard SHALL render those details in collapsible or visually distinct sections so the final chat response remains easy to read

#### Scenario: Resume event stream
- **WHEN** a user reconnects to an in-progress or completed job with a known event cursor
- **THEN** the dashboard SHALL request events after that cursor when supported and render the resumed transcript without duplicating already displayed events

### Requirement: DragnCards iframe panel
The dashboard SHALL provide an optional collapsible iframe panel for the DragnCards UI associated with the selected game session.

#### Scenario: Show DragnCards room
- **WHEN** the selected session has DragnCards room metadata or a room URL
- **THEN** the dashboard SHALL render a collapsible iframe panel that points to the corresponding DragnCards frontend URL

#### Scenario: Missing room URL
- **WHEN** no DragnCards room URL can be determined for the selected session
- **THEN** the dashboard SHALL show a clear empty state and SHALL keep chat and configuration usable

### Requirement: Merged Swagger playground
The dashboard SHALL provide a Swagger section that displays a merged OpenAPI document for agent-orchestrator and game-service and routes playground calls through dashboard proxy routes.

#### Scenario: View merged OpenAPI document
- **WHEN** a user opens the Swagger section
- **THEN** the dashboard SHALL fetch or serve a merged OpenAPI document containing the configured agent-orchestrator and game-service APIs

#### Scenario: Proxy playground request
- **WHEN** a user executes an API request from the Swagger playground
- **THEN** the dashboard SHALL proxy the request to the matching upstream service and return the upstream response to the playground

#### Scenario: Upstream spec unavailable
- **WHEN** one configured service OpenAPI document cannot be fetched
- **THEN** the dashboard SHALL still report the error clearly and SHALL render any available service specs when possible

### Requirement: Dashboard service configuration
The dashboard SHALL use non-secret environment configuration for service base URLs, DragnCards frontend URL, OpenAPI source paths, and default session settings.

#### Scenario: Load service endpoints from environment
- **WHEN** the dashboard starts
- **THEN** it SHALL read agent-orchestrator, game-service, and DragnCards frontend base URLs from environment-backed configuration

#### Scenario: Missing required service configuration
- **WHEN** required dashboard service URLs are missing
- **THEN** the dashboard SHALL show a clear configuration error instead of silently sending requests to an invalid target
