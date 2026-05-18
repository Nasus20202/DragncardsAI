# Dashboard Delta Spec

## MODIFIED Requirements

### Requirement: Dashboard application shell
The system SHALL provide a Next.js dashboard application with a dark-mode-capable HeroUI interface and top-level navigation for `Play`, `Games`, and `Swagger` sections.

#### Scenario: Navigate between dashboard sections
- **WHEN** a user opens the dashboard in a browser
- **THEN** the system SHALL display a top navbar with `Play`, `Games`, and `Swagger` navigation entries

## ADDED Requirements

### Requirement: Games session workspace
The dashboard SHALL provide a Games workspace with a left session sidebar and centre embedded iframe viewer, filling the full viewport height without page-level scrolling.

#### Scenario: View games layout
- **WHEN** a user opens the Games section on a desktop viewport
- **THEN** the dashboard SHALL show a game list on the left and an iframe viewer in the centre

### Requirement: Game session list
The dashboard SHALL fetch and display a list of active game sessions from the game-service `/games` endpoint.

#### Scenario: Games list shows active sessions
- **WHEN** a user opens the Games view
- **THEN** the dashboard SHALL fetch games from the game-service and display each session's room slug and plugin name

#### Scenario: Games list ordered by newest first
- **WHEN** multiple game sessions are active
- **THEN** the dashboard SHALL sort them by `created_at` descending before rendering the list

#### Scenario: Empty games list shown when no active sessions
- **WHEN** no game sessions are active
- **THEN** the dashboard SHALL display an empty state message

### Requirement: Embedded DragnCards iframe
The dashboard SHALL embed the DragnCards frontend in an iframe, showing the selected game room.

#### Scenario: Iframe loads selected game
- **WHEN** a game is selected in the Games view
- **THEN** the dashboard SHALL render an iframe pointing to the DragnCards frontend URL using the `/room/{room_slug}` path

#### Scenario: Placeholder shown when no game selected
- **WHEN** no game is selected
- **THEN** the dashboard SHALL display a placeholder in the iframe area indicating no game is selected

### Requirement: DragnCards frontend URL configuration
The dashboard SHALL read the DragnCards frontend URL from the `DRAGNCARDS_FRONTEND_URL` environment variable.

#### Scenario: Missing frontend URL uses local development default
- **WHEN** the DRAGNCARDS_FRONTEND_URL environment variable is not set
- **THEN** the dashboard SHALL fall back to `http://localhost:3000` for the embedded iframe target
