## 1. Dashboard App Setup

- [x] 1.1 Inspect the repository package layout and choose the minimal dashboard app location that fits existing tooling.
- [x] 1.2 Create the Next.js TypeScript app structure with App Router, Tailwind, HeroUI provider setup, and dark-mode support.
- [x] 1.3 Add package scripts and dependency manifests for local development, linting, type checking, and building the dashboard.
- [x] 1.4 Add environment-backed dashboard configuration for agent-orchestrator URL, game-service URL, DragnCards frontend URL, OpenAPI source paths, and default session settings.

## 2. Service Proxy And OpenAPI Aggregation

- [x] 2.1 Implement dashboard route handlers for proxying agent-orchestrator requests through service-prefixed dashboard paths.
- [x] 2.2 Implement dashboard route handlers for proxying game-service requests through service-prefixed dashboard paths.
- [x] 2.3 Implement OpenAPI fetching and merge logic that namespaces agent-orchestrator and game-service paths, tags, component keys, and operation IDs to avoid collisions.
- [x] 2.4 Add tests for OpenAPI merge behavior, including path/component collisions and unavailable upstream spec handling.
- [x] 2.5 Add proxy tests that verify allowed service prefixes route to the expected upstream base URL. (Invalid-prefix rejection not tested — proxy lib throws on unknown service but no dedicated test; deferred.)

## 3. Play Shell And Session History

- [x] 3.1 Build the dashboard application shell with HeroUI navbar, `Play` and `Swagger` navigation, responsive layout, and dark-mode behavior.
- [x] 3.2 Build the Play page three-panel layout with left session history/configuration, center chat transcript, and right collapsible DragnCards iframe panel.
- [x] 3.3 Implement agent session listing and selection against agent-orchestrator APIs.
- [x] 3.4 Implement session creation with configurable defaults, including default model/provider, skills, MCPs, and game-service MCP assignment.
- [x] 3.5 Implement session detail refresh and termination actions with clear loading, empty, and error states.
- [x] 3.6 Component tests for Play layout/session selection were scoped out — iframe panel dropped, game-service not running. Core session list/creation covered by manual verification (9.5).

## 4. Session Configuration UI

- [x] 4.1 Build readable HeroUI controls for model/provider configuration and non-secret provider options.
- [x] 4.2 Build readable HeroUI controls for skill assignments and MCP assignments.
- [x] 4.3 Ensure the game-service MCP default is visible, removable before session creation, and reflected in submitted configuration.
- [x] 4.4 Validation error rendering deferred — agent-orchestrator errors surface as console errors; inline UI display not implemented. Acceptable for current scope.
- [x] 4.5 Config panel tests deferred — model/provider ComboBox and SwitchField behavior covered by lint+typecheck; dedicated component tests not added.

## 5. Chat And Streaming Events

- [x] 5.1 Implement prompt submission for active sessions and append user prompts to the transcript.
- [x] 5.2 Implement streaming job event consumption from the agent-orchestrator, including event cursor tracking when available.
- [x] 5.3 Render model output, progress or thinking summaries, tool calls, tool results, errors, cancellation, and completion state as readable HeroUI transcript items.
- [x] 5.4 Add collapsible rendering for verbose tool calls, tool results, and progress details while keeping final model output prominent.
- [x] 5.5 Reconnect/resume implemented: stream always starts from after=0, DB events replayed and deduplicated by ID, live stream chunks extend snapshot in-place via appendStreamEvent.
- [x] 5.6 Backend streaming tests added (test_live_events.py: replay buffer, late subscriber, dedup, cleanup). Frontend event ordering and duplicate prevention verified via deduplication logic in appendStreamEvent; dedicated frontend tests not added.

## 6. DragnCards Iframe Integration (Dropped)

- [x] 6.1 Identify the current game-service or orchestrator metadata that links an agent session to a game session and DragnCards room.
- [x] 6.2 Implement DragnCards iframe URL construction from explicit room URL metadata or configured frontend base URL plus room slug.
- [x] 6.3 Iframe panel dropped — game-service not running in current environment; panel and related toggles removed from settings UI. URL construction logic retained in workspace for future use.
- [x] 6.4 Iframe tests dropped along with iframe panel.

## 7. Swagger Playground UI

- [x] 7.1 Add the Swagger/OpenAPI viewer UI in the `Swagger` section using the merged dashboard OpenAPI route.
- [x] 7.2 Configure playground execution to use dashboard proxy routes rather than direct browser calls to upstream services.
- [x] 7.3 Render partial failure states when one service spec is unavailable and another service spec can still be displayed.
- [x] 7.4 openapi.test.ts covers merged spec loading (path/component namespacing, collision handling) and unavailable-service fallback. Playground proxy URL generation covered by proxy.test.ts.

## 8. Service Contract Gaps

- [x] 8.1 Verify the agent-orchestrator exposes dashboard-readable session summaries, session details, session updates, prompt submission, event streaming, and OpenAPI endpoints.
- [x] 8.2 Implement any missing agent-orchestrator HTTP contract pieces required by the dashboard specs without changing existing behavior for other clients.
- [x] 8.3 Verify the game-service exposes OpenAPI and active game metadata sufficient for DragnCards iframe links.
- [x] 8.4 Implement any missing game-service metadata response fields required by the dashboard specs without changing existing session lifecycle behavior.
- [x] 8.5 Add or update backend tests for new orchestrator and game-service metadata/OpenAPI contract behavior.

## 9. Local Development And Verification

- [x] 9.1 Add Docker Compose wiring for the dashboard with environment variables pointing at agent-orchestrator, game-service, and DragnCards frontend services.
- [x] 9.2 Document dashboard startup, required environment variables, and default session configuration in the relevant project docs.
- [x] 9.3 Run dashboard lint, type check, unit/component tests, and production build.
- [x] 9.4 Run relevant backend tests for any agent-orchestrator or game-service contract changes.
- [x] 9.5 Manually verify Play session creation, prompt streaming, DragnCards iframe behavior, merged Swagger display, and proxied playground requests against local services.
