## 1. Terminate and hide sessions from the play session list

- [x] 1.1 Add a per-session terminate/remove control (hover/row action) to `play-session-list.tsx`
- [x] 1.2 Confirm the destructive action before terminating
- [x] 1.3 Wire the control through `play-workspace.tsx` to the existing terminate flow
- [x] 1.4 Filter terminated sessions out of the sidebar by default

## 2. Preserve last-used settings when creating a new session

- [x] 2.1 Seed new-session creation from the last-used draft instead of config defaults
- [x] 2.2 Fall back to config defaults when there is no prior draft/session
- [x] 2.3 Keep the change pure frontend (no new API calls)

## 3. Add scroll lock to the play transcript

- [x] 3.1 Track a near-bottom "locked" state from the scroll container's scroll event
- [x] 3.2 Auto-scroll only while locked
- [x] 3.3 Show a "Jump to latest" control when unlocked that re-locks and scrolls to bottom

## 4. Degrade gracefully when some providers are unavailable

- [x] 4.1 Replace the initial-load `Promise.all` with resilient settled loading
- [x] 4.2 Surface unavailable/failed providers as a non-blocking notice
- [x] 4.3 Default the provider/model selectors to a working provider and keep model selection enabled

## 5. Verify

- [x] 5.1 `pnpm lint`
- [x] 5.2 `pnpm typecheck`
- [x] 5.3 `pnpm build`
- [x] 5.4 `openspec validate dashboard-session-ux --strict`
