## MODIFIED Requirements

### Requirement: Dashboard application shell
The system SHALL provide a Next.js dashboard application with a dark-mode-capable HeroUI interface and top-level navigation for `Play`, `Games`, `History`, and `Swagger` sections, plus an entry linking out to the Bifrost gateway UI.

#### Scenario: Navigate between dashboard sections
- **WHEN** a user opens the dashboard in a browser
- **THEN** the system SHALL display a top navbar with `Play`, `Games`, `History`, and `Swagger` navigation entries

#### Scenario: Use dark mode
- **WHEN** the user enables dark mode or the browser prefers dark mode
- **THEN** the dashboard SHALL render the application shell and main content using dark-compatible HeroUI styling

## ADDED Requirements

### Requirement: Bifrost gateway UI link
The dashboard navigation SHALL include a `Bifrost` entry that opens the Bifrost AI gateway's own web UI. Because Bifrost is a separate application rather than a dashboard route, the entry SHALL open in a new browsing context using `target="_blank"` together with `rel="noopener noreferrer"`, SHALL carry a marker indicating it leaves the dashboard, and SHALL never be rendered in the active-route state. The entry SHALL render with the same typography, spacing, and hover treatment as the internal navigation entries.

The gateway UI address SHALL be read from the `BIFROST_UI_URL` environment variable and exposed on the public dashboard configuration. This address is the browser-reachable one and SHALL be configured independently of the services' Docker-internal `BIFROST_URL`.

#### Scenario: Bifrost entry opens the gateway UI in a new tab
- **WHEN** a user views the dashboard navigation
- **THEN** the dashboard SHALL render a `Bifrost` entry whose href is the configured Bifrost UI URL, with `target="_blank"` and `rel="noopener noreferrer"`

#### Scenario: Bifrost entry matches the internal navigation styling
- **WHEN** the `Bifrost` entry is rendered
- **THEN** it SHALL use the same idle navigation styling as the internal entries and SHALL NOT be highlighted as the active route

#### Scenario: Missing Bifrost UI URL uses local development default
- **WHEN** the `BIFROST_UI_URL` environment variable is not set
- **THEN** the dashboard SHALL fall back to `http://localhost:4003` as the Bifrost UI target

#### Scenario: Configured Bifrost UI URL is honoured
- **WHEN** `BIFROST_UI_URL` is set to a deployment-specific address
- **THEN** the dashboard SHALL use that address as the Bifrost UI target
