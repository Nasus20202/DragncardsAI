## 1. Configuration

- [x] 1.1 Add DRAGNCARDS_FRONTEND_URL to dashboard config
- [x] 1.2 Update dashboard config API endpoint to expose the frontend URL

## 2. Games API Client

- [x] 2.1 Create games API client to fetch games from game-service `GET /games`
- [x] 2.2 Add Games type definition for game session data

## 3. Games Workspace Components

- [x] 3.1 Create `/app/games/page.tsx` route
- [x] 3.2 Create `features/games/components/games-workspace.tsx`
- [x] 3.3 Create `features/games/components/games-session-list.tsx` for the game list
- [x] 3.4 Create `features/games/components/dragncards-iframe.tsx` for the embedded viewer
- [x] 3.5 Create `features/games/lib/use-games.ts` hook for games data fetching

## 4. Navigation

- [x] 4.1 Add "Games" nav entry to `features/shell/components/app-shell.tsx`

## 5. Tests

- [x] 5.1 Add unit test for games API client
- [x] 5.2 Add component test for games session list
- [x] 5.3 Add component test for games workspace