## Context

`game-service`, `agent-orchestrator`, and `dashboard` currently start without a shared telemetry bootstrap, and the repo-managed Bifrost gateway is also running without OpenTelemetry export, so local debugging relies on ad hoc logs and manual API inspection. The repository already has clear service boundaries and dedicated data stores for `agent-orchestrator` (PostgreSQL and Valkey) plus Valkey-backed coordination in `game-service`, which makes this a good point to add consistent tracing and metrics before more cross-service behavior is added.

The change is cross-cutting: it affects two Python services, one Next.js service, the repo-managed Bifrost gateway, and Docker Compose infrastructure. It also needs to account for upstream DragnCards services that we call but do not control, especially the Phoenix/WebSocket interaction surface in `game-service`.

## Goals / Non-Goals

**Goals:**

- Add a local telemetry backend based on `grafana/otel-lgtm:0.27.1` to the repo's Docker Compose stack.
- Emit OTLP traces and metrics from `game-service`, `agent-orchestrator`, and `dashboard` with stable `service.name` attribution.
- Enable Bifrost's OTel plugin so gateway-side GenAI traces and OTLP metrics are exported into the same local stack.
- Cover the highest-value runtime surfaces first: inbound HTTP, outbound HTTP, background work, PostgreSQL access, Valkey access, and key DragnCards session flows.
- Make telemetry configuration consistent across services by using standard OpenTelemetry environment variables and safe local defaults.
- Preserve a low-friction developer workflow: `docker compose up` should bring up the telemetry backend and the three first-party services should begin exporting without per-service manual setup.

**Non-Goals:**

- Browser-side real user monitoring or frontend client telemetry.
- Instrumentation for upstream containers under `external/`, including the DragnCards backend/frontend and plugin build pipeline.
- Production deployment, retention tuning, auth, dashboards-as-code, or alerting policy.
- Exhaustive custom domain metrics for every game event in the first pass.

## Decisions

### Decision: Standardize on OTLP export to a dedicated local LGTM service

All first-party services will export telemetry to a new Compose service, tentatively named `otel-lgtm`, running `grafana/otel-lgtm:0.27.1`. Services inside Compose will send OTLP over HTTP to `http://otel-lgtm:4318`, and the stack will expose a non-conflicting host Grafana port for local inspection. Bifrost will use the same collector through its built-in `otel` plugin.

This keeps ingestion, storage, and UI in one local dependency and avoids needing separate Jaeger, Prometheus, and Loki containers during the initial rollout.

Alternatives considered:

- Direct Jaeger plus Prometheus containers: rejected because it adds more Compose complexity and more per-service exporter configuration for no local-development benefit.
- Sending telemetry to a hosted SaaS backend: rejected because the request is specifically for a local stack and the repo currently favors self-contained local development.

### Decision: Use standard OpenTelemetry SDK bootstrap per runtime, with auto-instrumentation first and manual spans for repo-specific flows

For the Python services, startup will initialize a shared telemetry bootstrap that configures `TracerProvider`, `MeterProvider`, OTLP exporters, resource attributes, and logging correlation. Auto-instrumentation will cover FastAPI/ASGI, `httpx`, and SQLAlchemy where available. Manual spans will wrap important internal operations that are not covered well by generic instrumentors, especially `game-service` session lifecycle operations, DragnCards WebSocket action boundaries, and the custom raw RESP Valkey clients used by both services.

For `dashboard`, the server runtime will initialize telemetry through Next.js startup hooks so server-side route handlers, proxy requests, and server fetches can emit telemetry without introducing browser telemetry.

For Bifrost, the implementation will use the documented gateway `otel` plugin in `services/bifrost/config.json` rather than attempting to wrap the container externally. The plugin configuration will use `trace_type: genai_extension`, `protocol: http`, `collector_url` targeting the local collector, and push-based metrics with `metrics_enabled: true` and a dedicated OTLP metrics endpoint.

Alternatives considered:

- Manual spans only: rejected because HTTP, database, and common runtime coverage would be incomplete and inconsistent across services.
- Auto-instrumentation only: rejected because the repo has custom Valkey RESP clients and game/session flows whose most useful spans are application-level rather than library-level.
- Sidecar-style inference of Bifrost telemetry without configuring the gateway: rejected because Bifrost already ships a native OTel plugin with richer GenAI semantic data and push-based metrics.

### Decision: Keep configuration mostly on standard `OTEL_*` environment variables

The implementation will prefer standard OpenTelemetry environment variables such as `OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_RESOURCE_ATTRIBUTES`, and `OTEL_SDK_DISABLED`, with service-local bootstrap code only filling repo defaults when values are absent. For Bifrost, the plugin-specific JSON fields will point at the same collector while still using `OTEL_RESOURCE_ATTRIBUTES` for shared resource metadata. This keeps the configuration portable and makes local Compose, direct local runs, and future CI usage behave consistently.

Alternatives considered:

- A completely custom `DRAGNCARDSAI_TELEMETRY_*` config surface: rejected because it duplicates existing OpenTelemetry conventions and makes future tooling interoperability worse.
- Hard-coded exporter endpoints in code: rejected because local direct runs and test environments need overrideable endpoints.

### Decision: Instrument first-party dependencies that provide immediate debugging value

The initial instrumentation surface will include:

- `game-service`: inbound FastAPI requests, outbound `httpx` calls to DragnCards auth/endpoints, session restore/startup flows, game action execution boundaries, and Valkey session-store commands.
- `agent-orchestrator`: inbound FastAPI requests, outbound Bifrost and MCP HTTP calls, worker loop/job execution spans, SQLAlchemy/PostgreSQL spans, and Valkey live-event bus commands.
- `dashboard`: Next.js server startup, route handlers, upstream proxy requests to `agent-orchestrator` and `game-service`, and server-side fetch/http spans.
- `bifrost`: native GenAI traces for provider/model requests plus push-based gateway metrics exposed through the OTel plugin.

This scope intentionally prioritizes traces and metrics that explain latency and failure hotspots visible to developers today.

Alternatives considered:

- Instrument only the HTTP layer: rejected because PostgreSQL, Valkey, and worker/runtime behavior are explicitly part of the requested value.
- Instrument upstream DragnCards services in this change: rejected because those services live under `external/` and are out of scope for direct repository changes.

### Decision: Enable telemetry by default in Docker Compose and keep local opt-out available

The root compose stack will wire telemetry env vars into the three first-party services and configure the Bifrost `otel` plugin so telemetry works by default when the Docker stack is running. Direct local runs can disable application telemetry with `OTEL_SDK_DISABLED=true` or point at a different collector endpoint, while Bifrost can be disabled by removing or disabling the plugin configuration.

Alternatives considered:

- Opt-in telemetry disabled by default: rejected because it would make verification harder and reduce the chance that telemetry remains exercised during normal development.
- No opt-out path: rejected because isolated tests and local debugging sometimes need to bypass exporters.

## Risks / Trade-offs

- [Next.js startup ordering can be sensitive] -> Initialize telemetry through the framework-supported server startup hook and keep browser instrumentation out of scope to reduce runtime surprises.
- [The repo uses custom raw RESP Valkey clients instead of a standard library] -> Add manual spans and counters around command execution rather than waiting for a non-existent automatic instrumentor.
- [DragnCards WebSocket behavior is upstream and not under our control] -> Instrument only the client-side boundaries we own, including connect, join, action push, and state wait phases, and treat the upstream backend as an external black box.
- [Bifrost plugin config lives in JSON rather than environment-only runtime code] -> Keep the plugin config minimal, use env substitution only for values that must stay external, and document the expected local collector endpoints.
- [Telemetry noise or high-cardinality attributes can reduce usefulness] -> Limit attributes to stable identifiers such as service name, operation name, dependency kind, and sanitized session/job context instead of raw payload dumps.
- [Local LGTM increases Compose footprint] -> Keep the stack local-only, use a single combined image, and avoid adding custom dashboards or extra collectors in the first pass.

## Migration Plan

1. Add the `otel-lgtm` service and non-conflicting host port mappings in Compose.
2. Add runtime dependencies and telemetry bootstrap code to `game-service` and `agent-orchestrator`.
3. Add server-side telemetry bootstrap to `dashboard`.
4. Configure the Bifrost `otel` plugin in `services/bifrost/config.json` for `genai_extension` traces and push-based metrics.
5. Wire shared `OTEL_*` environment variables through Compose and document direct-run overrides.
6. Add verification coverage for bootstrap/config and a local smoke workflow that confirms telemetry reaches LGTM.

Rollback strategy:

- Set `OTEL_SDK_DISABLED=true` for the affected services to stop export without removing code.
- Remove the `otel-lgtm` service, telemetry env wiring, and the Bifrost `otel` plugin configuration if a full rollback is needed.
- Dependency additions remain isolated to the three first-party services and can be reverted independently if one runtime proves problematic.

## Open Questions

- Whether the local Grafana host port should be `3004` or another unused value in the team workflow; the implementation should choose a non-conflicting default.
- Whether any low-cardinality custom counters should be included in the first pass for worker job outcomes or game action categories, or whether the rollout should stay strictly with runtime/dependency telemetry plus manual spans.
- Whether the Bifrost collector URL should use the bare OTLP HTTP endpoint or explicit `/v1/traces` and `/v1/metrics` paths in local config; implementation should follow the plugin behavior that works cleanly with `otel-lgtm`.
