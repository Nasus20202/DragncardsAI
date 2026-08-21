# Dashboard

## MODIFIED Requirements

### Requirement: Games session workspace
The dashboard SHALL provide a Games workspace with a left session sidebar and centre embedded game viewer, filling the full viewport height without page-level scrolling.

The centre viewer SHALL be selected by the platform of the game the user selected, so the workspace layout is the same for every platform while the embedded target is not.

#### Scenario: View games layout
- **WHEN** a user opens the Games section on a desktop viewport
- **THEN** the dashboard SHALL show a game list on the left and an embedded game viewer in the centre

#### Scenario: The viewer follows the selected game's platform
- **WHEN** a user selects a game whose platform is `marvel-lcg` and then selects a game whose platform is `dragncards`
- **THEN** the centre viewer SHALL embed the target of the selected game's platform in each case, and the surrounding workspace layout SHALL be unchanged between the two

### Requirement: Game session list
The dashboard SHALL fetch and display a list of active game sessions from the game-service `/games` endpoint.

Each row SHALL state which platform the game belongs to, because the platform determines what every other control on the row does — which viewer opens, whether a room slug exists, and which move surface the agent drove. A session whose platform the game-service does not report SHALL be presented as `dragncards`, which is the platform every session recorded before platform support existed.

A row SHALL show only the identifiers its platform actually has: a DragnCards session's room slug and plugin name, and for a platform with neither, the platform's own game identifier. The dashboard SHALL NOT render an empty room slug or an invented plugin name for a platform that has no such concept.

#### Scenario: Games list shows active sessions
- **WHEN** a user opens the Games view
- **THEN** the dashboard SHALL fetch games from the game-service and display each session's platform together with the identifiers that platform provides — for a DragnCards session its room slug and plugin name

#### Scenario: Games list ordered by newest first
- **WHEN** multiple game sessions are active
- **THEN** the dashboard SHALL sort them by `created_at` descending before rendering the list

#### Scenario: Empty games list shown when no active sessions
- **WHEN** no game sessions are active
- **THEN** the dashboard SHALL display an empty state message

#### Scenario: A marvel-lcg session shows no room slug or plugin name
- **WHEN** the games list renders a session whose platform is `marvel-lcg`
- **THEN** the row SHALL name the platform and the platform's own game identifier
- **AND** the row SHALL render no room slug and no plugin name rather than rendering blank or placeholder values for them

#### Scenario: A session reporting no platform reads as DragnCards
- **WHEN** the games list renders a session whose response carries no `platform` field
- **THEN** the row SHALL present it as a `dragncards` game

## ADDED Requirements

### Requirement: Per-platform embedded game viewer
The dashboard SHALL resolve the embedded viewer target for a selected game from that game's platform, through one per-platform resolver that is the only place a platform's viewer URL is composed. A component SHALL NOT compose a viewer URL itself, and the DragnCards `/room/<slug>` template SHALL remain the single copy it is today rather than being duplicated into a platform switch.

The resolver SHALL address each platform the way that platform is addressed:

- a `dragncards` game SHALL be addressed as `<dragncards frontend base>/room/<room_slug>`, unchanged from today;
- a `marvel-lcg` game SHALL be addressed on its own base URL, read-only as `<marvel-lcg base>/watch` by default, and as `<marvel-lcg base>/?p=<seat index>` only when the user deliberately takes a seat. A `marvel-lcg` game SHALL NOT be addressed by room slug, because that platform has no rooms.

The seat index SHALL be derived from the repository's neutral seat vocabulary at this edge only: `playerN` maps to `p=N-1`.

A selected game whose platform has no configured base URL, and a selected game whose platform the dashboard does not support, SHALL render an explanatory placeholder naming what is missing. The Games workspace SHALL remain usable in both cases and SHALL NOT fail to render, because a viewer that cannot be configured is not a reason the session list becomes unreachable.

#### Scenario: A DragnCards game is embedded by room slug
- **WHEN** a game whose platform is `dragncards` is selected in the Games view
- **THEN** the dashboard SHALL embed `<dragncards frontend base>/room/<room_slug>` using the single existing room-URL template

#### Scenario: A marvel-lcg game is embedded read-only by default
- **WHEN** a game whose platform is `marvel-lcg` is selected in the Games view and the user has not taken a seat
- **THEN** the dashboard SHALL embed `<marvel-lcg base>/watch`
- **AND** the embedded URL SHALL contain no room-slug path segment

#### Scenario: Taking a seat addresses that seat
- **WHEN** the user opens a `marvel-lcg` game as seat `player2`
- **THEN** the dashboard SHALL embed `<marvel-lcg base>/?p=1`

#### Scenario: A platform with no configured base URL explains itself
- **WHEN** a game is selected whose platform has no base URL configured
- **THEN** the viewer area SHALL render a placeholder naming the missing configuration setting, and the game list SHALL remain rendered and usable

#### Scenario: Placeholder shown when no game selected
- **WHEN** no game is selected
- **THEN** the dashboard SHALL display a placeholder in the viewer area indicating no game is selected

#### Scenario: An unrecognised platform is not guessed at
- **WHEN** a selected game reports a platform the dashboard does not support
- **THEN** the dashboard SHALL render a placeholder naming that platform, and SHALL NOT compose a viewer URL from another platform's template

### Requirement: Per-platform game viewer base URL configuration
The dashboard SHALL read one browser-facing base URL per supported game platform from its own environment variable, each defaulting to the value that works against the local stack: `DRAGNCARDS_FRONTEND_URL` defaulting to `http://localhost:3000`, and `MARVEL_LCG_BASE_URL` defaulting to `http://localhost:4006` to match the compose default published port.

These base URLs are iframe targets the browser loads directly. They are NOT first-party services the dashboard proxies: a game platform SHALL NOT be added to `SERVICE_KEYS` in `features/proxy/lib/proxy.ts`, which remains the single declaration of the services the dashboard fronts, and no second list of platforms or services SHALL be written beside it. Each new variable the dashboard configuration reads SHALL be cleared by `vitest.setup.ts`, so a suite's assertions describe the declared defaults rather than the machine running them.

#### Scenario: Missing DragnCards frontend URL uses local development default
- **WHEN** the `DRAGNCARDS_FRONTEND_URL` environment variable is not set
- **THEN** the dashboard SHALL fall back to `http://localhost:3000` for the DragnCards viewer target

#### Scenario: Missing marvel-lcg base URL uses local development default
- **WHEN** the `MARVEL_LCG_BASE_URL` environment variable is not set
- **THEN** the dashboard SHALL fall back to `http://localhost:4006` for the marvel-lcg viewer target

#### Scenario: A game platform is not a proxied service
- **WHEN** the dashboard's proxied-service declaration is inspected
- **THEN** `SERVICE_KEYS` SHALL contain only first-party backend services and SHALL contain no game platform
- **AND** no other module SHALL declare its own list of services or platforms alongside it

#### Scenario: New configuration variables are cleared by the frontend suite
- **WHEN** the dashboard test suite runs in a shell exporting a platform base URL
- **THEN** the suite SHALL clear that variable before each test, and the configuration guard SHALL fail if the configuration module reads a variable the suite does not clear

### Requirement: A game platform's debug and cheat surface is never reachable through the dashboard
marvel-lcg serves an unauthenticated `GET /debug` that reaches `exec()` behind a bypassable AST blocklist, and it additionally treats `debug` and `show` query parameters as cheat-mode switches. The dashboard SHALL offer no path to any of them.

The dashboard SHALL NOT proxy a game platform. Because a platform is absent from `SERVICE_KEYS`, a request to `/api/proxy/<platform>/...` SHALL be refused by the existing unknown-service check before any upstream connection is opened, and there SHALL be no alternative dashboard route, server action, or rewrite that forwards to a platform.

Every marvel-lcg URL the dashboard composes SHALL come from the per-platform viewer resolver, and that resolver SHALL emit only `/watch` or `/?p=<seat index>`. It SHALL NOT emit the `/debug` path, and SHALL NOT emit a `debug`, `show`, or `replay` query parameter. This SHALL be asserted by a test over the resolver's output rather than left to review, because the endpoint is remote code execution and the platform binds all interfaces.

#### Scenario: A platform is not reachable through the proxy
- **WHEN** a request is made to `/api/proxy/marvel-lcg/debug`
- **THEN** the proxy SHALL answer `404` for an unknown service and no upstream SHALL receive a request

#### Scenario: No composed viewer URL reaches the debug endpoint
- **WHEN** the per-platform viewer resolver is exercised over every supported platform, seat, and read-only combination
- **THEN** no produced URL SHALL contain the `/debug` path, and none SHALL carry a `debug`, `show`, or `replay` query parameter

#### Scenario: The dashboard has no other route to a platform
- **WHEN** the dashboard's routes, rewrites, and server-side fetch targets are inspected
- **THEN** none SHALL forward a request to a game platform's origin, so the embedded iframe is the only way a platform is reached from the browser

## REMOVED Requirements

### Requirement: Embedded DragnCards iframe
**Reason**: Replaced by "Per-platform embedded game viewer". The removed requirement made the viewer unconditionally a DragnCards iframe addressed by `/room/{room_slug}`, which is not how marvel-lcg is addressed — it has no rooms, and a viewer is opened on its own base URL as `/watch` or `/?p=<seat>`. Keeping a requirement that names one platform's URL template as *the* viewer behaviour would have left the spec describing a workspace that cannot show half the games in the list.

**Migration**: The behaviour it protected is preserved in "Per-platform embedded game viewer": a DragnCards game is still embedded at `<dragncards frontend base>/room/<room_slug>` through the same single room-URL template, and the no-game-selected placeholder scenario is carried over unchanged.

### Requirement: DragnCards frontend URL configuration
**Reason**: Replaced by "Per-platform game viewer base URL configuration". A single `DRAGNCARDS_FRONTEND_URL` requirement cannot express the second platform's base URL, and stating each platform's variable in its own requirement is what keeps the configuration and the viewer resolver in step.

**Migration**: `DRAGNCARDS_FRONTEND_URL` and its `http://localhost:3000` default are unchanged and are now stated by the replacing requirement, alongside `MARVEL_LCG_BASE_URL`.
