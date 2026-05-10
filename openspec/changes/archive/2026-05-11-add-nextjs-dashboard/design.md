## Context

The repository currently centers on backend services: `game-service` exposes FastAPI HTTP and MCP access to DragnCards sessions, while `agent-orchestrator` manages LLM sessions, model/provider configuration, assigned skills, MCPs, prompt jobs, and streaming events. Users who want to configure an agent and play through a game need to combine API calls, service logs, and the separate DragnCards frontend manually.

The dashboard should be a thin browser application over these existing services. It must keep the service contracts visible, provide a readable chat/playground experience, and avoid hiding orchestration details that are important for debugging LLM gameplay. The implementation should prefer straightforward server-side proxy routes and typed client state over a large custom frontend architecture.

## Goals / Non-Goals

**Goals:**

- Add a Next.js TypeScript dashboard app that uses HeroUI and Tailwind utilities for UI implementation.
- Provide a dark-mode-capable shell with top-level `Play` and `Swagger` navigation.
- Let users create, select, configure, and run agent sessions backed by the agent-orchestrator.
- Render live orchestration output in a ChatGPT-like conversation, including thinking/progress, model output, tool calls, tool results, errors, and completion state.
- Embed the DragnCards UI in a collapsible right-side iframe when a game room URL is available.
- Provide a Swagger/OpenAPI playground with merged specs from agent-orchestrator and game-service, proxied through dashboard routes.
- Support configurable session defaults, including default model/provider settings, default MCP assignments, default skills, and the default game-service MCP.

**Non-Goals:**

- Build authentication, authorization, or user-specific persistence.
- Replace the existing DragnCards frontend or render the board natively in the dashboard.
- Add a custom styling system beyond HeroUI theme setup and Tailwind utility classes.
- Change upstream DragnCards backend behavior or Phoenix channel semantics.
- Guarantee production-hardening for arbitrary third-party OpenAPI specs in the first iteration.

## Decisions

### Use a standalone Next.js app with App Router

Create the dashboard as a separate app package using Next.js App Router, TypeScript, HeroUI, and Tailwind. Keep most UI in client components where live session state and streaming output are needed, and use route handlers for service proxying and OpenAPI merging.

Alternatives considered: A static React/Vite app was simpler to serve, but it would either expose service URLs directly to the browser or require a separate proxy service. Building the UI into a Python service was rejected because it couples frontend iteration to backend runtime concerns and does not align with HeroUI/Next.js usage.

### Keep the dashboard as a thin proxy over existing services

Dashboard route handlers should proxy requests to `agent-orchestrator` and `game-service` using environment-configured base URLs. The browser should call dashboard-relative routes so local development avoids CORS friction and Swagger playground requests can be routed consistently.

Alternatives considered: Direct browser-to-service calls reduce server code but create CORS/configuration complexity and make merged Swagger playground calls harder. A dedicated API gateway was rejected as unnecessary for a local developer dashboard.

### Model the Play page around sessions, events, and panels

The Play page should use a three-panel layout: session history/configuration on the left, live chat transcript in the center, and a collapsible DragnCards iframe on the right. The center transcript should preserve event readability by grouping model output, thinking/progress, tool calls, tool results, and errors into distinct HeroUI cards or accordions.

Alternatives considered: A single-column chat UI is easier, but it hides session configuration and game context. A dense operations dashboard was rejected because the primary workflow is chat-driven gameplay, not raw monitoring.

### Treat thinking/progress as streamed diagnostic events

The dashboard should display thinking/progress only when the orchestrator emits event types intended for clients. It should not invent private chain-of-thought or infer hidden reasoning. Tool calls, tool results, and progress summaries should be collapsible to keep the transcript readable.

Alternatives considered: Showing only final model text is cleaner but loses critical observability for agent debugging. Rendering every raw event ungrouped was rejected because readability is a primary requirement.

### Merge OpenAPI specs at dashboard runtime

The Swagger section should fetch OpenAPI JSON from configured service endpoints, prefix paths or tags to prevent collisions, and expose the merged document through a dashboard route consumed by the UI viewer. Playground calls should go through dashboard proxy routes that map service-prefixed paths back to the correct upstream service.

Alternatives considered: Generating a checked-in merged spec would go stale as service APIs change. Showing separate Swagger viewers was rejected because the requested workflow is a single playground across services.

### Use environment-driven defaults instead of dashboard persistence

Initial session defaults should come from environment variables or a checked-in non-secret config module, including default provider/model, default skills, default MCPs, and default game-service MCP assignment. Runtime changes can be passed to service APIs when sessions are created or updated, but dashboard-specific persistence is out of scope.

Alternatives considered: Browser local storage is convenient but can make configuration hard to reproduce. A dashboard database was rejected as too much scope for a local playground and unnecessary without user accounts.

## Risks / Trade-offs

- [Risk] Service OpenAPI documents can have path, tag, component, or operation ID collisions when merged. -> Mitigation: namespace service paths and component keys during merge, and keep the original service name visible in tags.
- [Risk] Swagger playground proxying can accidentally forward unsupported paths or unsafe methods. -> Mitigation: allow only configured service prefixes and pass through request metadata without adding secrets client-side.
- [Risk] Agent streaming event schemas can evolve. -> Mitigation: render known event types richly and fall back to a readable generic event card for unknown types.
- [Risk] DragnCards room URLs or iframe embedding behavior can change upstream. -> Mitigation: derive iframe URLs from explicit service metadata where available, make the panel optional, and show a clear unavailable state instead of blocking chat.
- [Risk] The DragnCards WebSocket state can lag behind iframe rendering or game-service state. -> Mitigation: label iframe as the live DragnCards UI and keep game-service state/tool events visible in the transcript for auditability.
- [Risk] HeroUI and Next.js add a JavaScript toolchain to a mostly Python/Docker repository. -> Mitigation: isolate the dashboard in its own package with clear scripts and Docker wiring.

## Migration Plan

- Add the dashboard package and wire it into local development without changing existing service startup paths.
- Configure dashboard environment variables for orchestrator, game-service, DragnCards frontend, and default session settings.
- Add Docker Compose integration after the app runs locally, keeping existing services unchanged.
- Rollback by removing the dashboard service/package and related Compose/environment entries; backend services remain unaffected.

## Open Questions

- Which concrete endpoint currently returns the agent-orchestrator OpenAPI document, and is it stable enough for runtime merging?
- Does the orchestrator already expose catalog endpoints for supported providers, models, MCPs, skills, and default session configuration, or should the dashboard start from environment-configured defaults only?
- What exact game-service metadata should the dashboard use to construct the DragnCards iframe URL: room slug, full frontend URL, or both?
