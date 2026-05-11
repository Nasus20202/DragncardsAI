## 1. Local observability infrastructure

- [x] 1.1 Add an `otel-lgtm` service based on `grafana/otel-lgtm:0.27.1` to the local Compose stack with stable host port mappings for the observability UI and OTLP ingestion.
- [x] 1.2 Wire `OTEL_*` environment variables into `game-service`, `agent-orchestrator`, and `dashboard` in Compose, including per-service identity and the shared local OTLP endpoint.
- [x] 1.3 Configure the Bifrost `otel` plugin in `services/bifrost/config.json` for `genai_extension` traces plus push-based OTLP metrics to the local collector.
- [x] 1.4 Document the local observability URLs, service env defaults, and the opt-out path using `OTEL_SDK_DISABLED=true`.
- [x] 1.5 Document the Bifrost-specific telemetry settings, including the collector URL shape, trace format, metrics endpoint, and any env-backed resource attributes.

## 2. Shared Python telemetry bootstrap

- [x] 2.1 Add the OpenTelemetry SDK, OTLP exporters, and required Python instrumentation dependencies to `services/game-service` and `services/agent-orchestrator`.
- [x] 2.2 Implement a small shared telemetry bootstrap pattern in each Python service that initializes resources, tracer/meter providers, and log correlation only when telemetry is enabled.
- [x] 2.3 Add unit coverage for Python telemetry configuration so disabled mode and env overrides are both verified.

## 3. Game service instrumentation

- [x] 3.1 Instrument inbound FastAPI request handling and outbound `httpx` calls in `game-service`.
- [x] 3.2 Add manual spans around session restore, session creation, and action execution workflows in `game-service`.
- [x] 3.3 Add manual telemetry around the custom Valkey session-store command paths in `game-service`.
- [x] 3.4 Add or update tests that verify `game-service` telemetry bootstrap does not break HTTP startup paths.

## 4. Agent orchestrator instrumentation

- [x] 4.1 Instrument inbound FastAPI request handling, outbound Bifrost/MCP HTTP calls, and SQLAlchemy database access in `agent-orchestrator`.
- [x] 4.2 Add manual spans around worker job claim, execution, downstream call, and completion/failure boundaries.
- [x] 4.3 Add manual telemetry around the custom Valkey live-event bus command paths in `agent-orchestrator`.
- [x] 4.4 Add or update tests that verify telemetry bootstrap does not break repository initialization, worker startup, or readiness-sensitive code paths.

## 5. Dashboard server instrumentation

- [x] 5.1 Add the required Node.js OpenTelemetry dependencies and server-side bootstrap for the Next.js dashboard runtime.
- [x] 5.2 Instrument dashboard route handlers and proxy/upstream server fetch paths so requests to `agent-orchestrator` and `game-service` emit telemetry.
- [x] 5.3 Add or update dashboard tests or config checks to verify the server telemetry bootstrap loads without breaking lint, typecheck, or test workflows.

## 6. End-to-end verification

- [x] 6.1 Add a local smoke verification step that starts the stack, exercises each first-party service plus Bifrost, and confirms telemetry reaches the LGTM backend.
- [x] 6.2 Add integration-oriented verification for at least one traced PostgreSQL path and one traced Valkey path in the instrumented services.
- [x] 6.3 Verify that Bifrost gateway traces and pushed metrics appear in the local observability stack after an agent-orchestrator request flows through the gateway.
- [x] 6.4 Run the relevant repo test and validation commands for the touched services and update docs or troubleshooting notes for any telemetry-specific caveats discovered during rollout.
