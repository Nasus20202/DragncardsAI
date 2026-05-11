## Why

The repository currently has no consistent telemetry across `game-service`, `agent-orchestrator`, `dashboard`, and the repo-managed Bifrost gateway, which makes it hard to diagnose latency, runtime failures, external dependency issues, and background-job behavior in local development. Adding OpenTelemetry now gives the team a shared observability baseline before the system grows further and before more service interactions become harder to debug.

## What Changes

- Add OpenTelemetry-based traces, metrics, and structured log correlation for the three first-party services: `game-service`, `agent-orchestrator`, and `dashboard`.
- Enable the Bifrost gateway's built-in `otel` plugin so gateway-side LLM traces and push-based metrics are exported into the same local observability stack.
- Export telemetry to a local `grafana/otel-lgtm:0.27.1` stack running in Docker Compose so developers can inspect traces and metrics without external SaaS dependencies.
- Instrument high-value runtime surfaces including inbound HTTP requests, outbound HTTP calls, background work, WebSocket-facing session flows, PostgreSQL access, and Valkey access where those dependencies exist, while also collecting Bifrost GenAI traces and gateway metrics.
- Define a shared telemetry configuration contract for service name, exporter endpoint, enable/disable controls, Bifrost plugin settings, and safe defaults for local development.
- Add verification coverage so the stack can be started locally and telemetry emission can be validated during development and test workflows.

## Capabilities

### New Capabilities
- `observability`: Cross-service OpenTelemetry requirements for runtime tracing, metrics, dependency instrumentation, Bifrost gateway telemetry, and local telemetry export.

### Modified Capabilities
- `infrastructure`: Local Docker Compose infrastructure will add and configure a Grafana LGTM stack plus telemetry wiring for application services and the Bifrost gateway.

## Impact

- Affected code: `services/game-service/`, `services/agent-orchestrator/`, `services/dashboard/`, `services/bifrost/config.json`, root compose files, and service runtime configuration.
- Affected systems: local Docker Compose stack, Python runtimes, Next.js runtime, Bifrost gateway runtime, PostgreSQL, Valkey, HTTP client/server paths, and background job execution.
- New dependencies: OpenTelemetry SDKs/instrumentation packages for Python and Node.js, plus local LGTM infrastructure image `grafana/otel-lgtm:0.27.1`.
- Operational impact: developers gain local traces/metrics visibility and correlated telemetry for debugging, while production rollout remains out of scope for this change.

## Non-Goals

- Production-grade telemetry backends, retention policies, authentication, or hosted observability rollout.
- Changes to upstream DragnCards services under `external/`.
- Large-scale custom business metrics beyond the initial high-value runtime and dependency coverage.
