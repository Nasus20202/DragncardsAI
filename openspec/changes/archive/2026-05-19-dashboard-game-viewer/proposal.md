## Why

During development and testing of the DragnCardsAI bot, there is no convenient way to visually monitor active game sessions. Developers must manually navigate to the DragnCards web UI with the correct room slug to observe game state, which is cumbersome and disconnects the observation experience from the dashboard.

## What Changes

- **New Dashboard View**: Add a `Games` section to the dashboard that lists active game sessions from `game-service`
- **Game List Display**: Show each game by room slug with plugin name, ordered by newest first
- **Embedded Game Viewer**: Render a single iframe for the selected game that loads the DragnCards frontend room route
- **New Capability**: Extend the dashboard with lightweight game observation functionality

## Capabilities

### New Capabilities
None. This extends the existing `dashboard` capability.

### Modified Capabilities
- `dashboard`: Add a Games view for listing active game sessions with an embedded DragnCards iframe viewer

## Impact

- Affects `openspec/specs/dashboard/spec.md` by adding the Games route and game-viewer behavior
- Requires dashboard UI components for the game list and iframe container
- Requires integration with `GET /games`
- Uses `DRAGNCARDS_FRONTEND_URL` for the iframe target and falls back to `http://localhost:3000` for local development when it is unset
