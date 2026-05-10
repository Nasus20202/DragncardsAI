## Why

DragnCardsAI needs a human-friendly dashboard for configuring agent sessions, playing through orchestrated chat interactions, and observing game state without stitching together raw API calls and logs. A focused Next.js frontend will make the agent-orchestrator and game-service usable as an interactive playground while preserving clear visibility into sessions, model choices, MCPs, skills, tool activity, and DragnCards UI state.

## What Changes

- Add a Next.js dashboard application using HeroUI components and Tailwind utility classes only, with no bespoke stylesheet layer beyond framework setup.
- Provide a dark-mode-capable application shell with a top navbar containing `Play` and `Swagger` sections.
- Build a `Play` workspace with session history on the left, a ChatGPT-like live conversation stream in the center, and a collapsible DragnCards iframe panel on the right.
- Expose session configuration controls for session defaults, selected model/provider, assigned MCP servers, assigned skills, and default game-service MCP behavior.
- Stream and render agent-orchestrator output clearly, including model text, thinking/progress events, tool calls, tool results, errors, and completion state.
- Add a `Swagger` workspace that presents merged OpenAPI specs for the agent-orchestrator and game-service and proxies playground calls through the dashboard backend.
- Keep the first implementation simple and readable: prioritize clear state, obvious controls, and low coupling over advanced visual customization.

## Non-goals

- Do not build a custom design system beyond HeroUI and Tailwind configuration.
- Do not replace the existing agent-orchestrator, game-service, or DragnCards frontend.
- Do not implement authentication, authorization, multi-tenant user management, or cloud deployment in this change.
- Do not add persisted dashboard-specific user accounts or long-term preference storage unless already supported by the existing backend contracts.
- Do not require the dashboard to generate or mutate service OpenAPI schemas; it should consume and merge exposed specs.

## Capabilities

### New Capabilities

- `dashboard`: Browser dashboard for session-centric play, configuration, service API exploration, OpenAPI aggregation, and service proxying.

### Modified Capabilities

- `agent-orchestrator`: The dashboard depends on existing and planned orchestrator session, configuration, job submission, and streaming event contracts; requirements are extended only where needed to support dashboard-readable metadata and defaults.
- `game-service`: The dashboard depends on the game-service OpenAPI document, game session metadata, and DragnCards room/UI links; requirements are extended only where needed for iframe/playground integration.

## Impact

- Adds a frontend application package to the repository, expected to use Next.js, HeroUI, Tailwind, TypeScript, and a Swagger UI or Scalar-style OpenAPI viewer dependency.
- Adds dashboard server routes or route handlers to merge OpenAPI specs and proxy requests to agent-orchestrator and game-service using environment-configured service base URLs.
- May add Docker Compose wiring and environment variables for dashboard service URLs, default MCP/session configuration, and DragnCards iframe URL construction.
- Requires integration checks against agent-orchestrator streaming endpoints and game-service session APIs, with unit/component tests for UI state where practical.
