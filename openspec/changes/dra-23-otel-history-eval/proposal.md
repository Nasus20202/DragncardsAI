# Emit OpenTelemetry from history-service and eval-service (DRA-23)

## Why

A user reported (DRA-23): *"OTel data is missing for history and eval services.
Update agent context to ensure that the OTel will be properly set up for each
services."*

Diagnosed. It is not a misconfiguration — it is missing code.

**The configuration was already correct.** `docker-compose.yaml` sets
`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`,
`OTEL_EXPORTER_OTLP_PROTOCOL` and `OTEL_RESOURCE_ATTRIBUTES` for both services,
pointing at the same `otel-lgtm` collector the working services use. Every
surface a reviewer would casually inspect looked right.

**There was no OpenTelemetry code at all.** Grepping
`services/history-service/{src,docker,pyproject.toml}` and
`services/eval-service/{src,docker,pyproject.toml}` for `instrument`, `tracer`,
`opentelemetry` and `otel` returns **zero** hits in each. The same grep over
`services/game-service/src` returns 49 hits and over
`services/agent-orchestrator/src` returns 63. Concretely, both services were
missing every one of:

- the OpenTelemetry packages in `pyproject.toml` (no SDK, no OTLP exporter, no
  instrumentation),
- a telemetry module, so no `TracerProvider`, `MeterProvider` or
  `LoggerProvider` was ever installed and the global no-op providers stayed in
  place,
- a `setup_telemetry()` call in the entrypoint,
- `FastAPIInstrumentor.instrument_app`, so no HTTP server spans or
  `http_server_*` metrics,
- SQLAlchemy instrumentation in `create_engine`, so no database spans or
  `db_client_connections_usage`,
- and, for history-service, a tracer on its Valkey client: it re-exported
  `dragncards_common.resp.RespConnection` directly, and that shared client emits
  a `valkey.execute` span only when it is handed a tracer, so the span code was
  present but dormant.

The two services therefore exported nothing — no traces, no metrics, no logs —
for their entire existence, while their environment claimed otherwise.

**Why nobody noticed.** The `observability` spec's requirements name
`game-service`, `agent-orchestrator`, `dashboard` and Bifrost explicitly, and
never mentioned the two newer services. A requirement that does not name a
service does not constrain it. Meanwhile the bootstrap lived as two byte-identical
~200-line copies inside `game-service` and `agent-orchestrator`, so wiring a new
service meant knowing to copy a file nobody had told you about. Nothing in
`AGENTS.md` named telemetry as a step when adding a service. The reporter's second
sentence is the more important half of the fix, and it is right.

## What Changes

- **The bootstrap becomes shared, once.** `dragncards_common.telemetry` now owns
  the three providers, the OTLP/HTTP exporters, the `service.name` resource, the
  `OTEL_SDK_DISABLED` no-op, the trace-correlated log formatting, and the
  FastAPI / httpx / SQLAlchemy instrumentation helpers. The FastAPI and SQLAlchemy
  instrumentors are imported lazily, so the shared library does not acquire a
  dependency on either framework.
- **history-service and eval-service are wired at every edge they own.** Each
  gains a thin `telemetry.py` binding its own `service.name` to the shared
  bootstrap, a `setup_telemetry()` call in `main.py`, `instrument_fastapi_app` in
  its app factory with `shutdown_telemetry()` in the lifespan teardown, and
  SQLAlchemy instrumentation in `create_engine`. history-service additionally
  subclasses the shared `RespConnection` to inject its tracer, which is what turns
  the dormant Valkey span code on.
- **Manual spans cover the workflows generic instrumentation cannot explain**, at
  the same granularity the working services use: `history.ingest_batch` (one span
  per polled batch, not per event — the ingester polls continuously),
  `history.take_snapshot`, `history.restore`, and `eval.evaluate_target` (one per
  graded target, carrying the judge outcome).
- **agent-orchestrator is migrated onto the shared bootstrap** and its duplicate
  copy deleted. Without this the change would have left a *third* identical copy,
  which is worse duplication than it started with. `game-service` keeps its own
  copy: it is the only Python service that does not depend on `dragncards-common`
  and its image installs from its own lockfile with `uv sync --frozen`, so
  migrating it means a dependency plus a Dockerfile change that cannot be verified
  without building the image. That is deliberately deferred and recorded here.
- **Span attributes are constrained and tested.** Only identifiers, scopes,
  counts, seqs, mode flags and outcome words may be attached. Tests pin the
  permitted attribute-key set for each workflow span, including one asserting that
  a gateway error carrying a bearer token and a prompt echo reaches the span as the
  single word `failed`.
- **The dashboard now propagates trace context to both services.** Found while
  auditing lists that enumerate services: `instrumentation.ts` listed only
  `agent-orchestrator`, `game-service`, `localhost:4001` and `localhost:4002` as
  `propagateContextUrls`, so a dashboard call to history-service or eval-service
  started a *separate* trace instead of a child span — the two halves never joined
  up. All four services and their host ports are now covered, behind a named
  exported helper so a test can assert the list rather than a reviewer reading it.
- **Ancillary files are brought current**: `depends_on: otel-lgtm` for both
  services in `docker-compose.yaml`; a commented, placeholder-only OpenTelemetry
  block in all four Python `.env.example` files; an Observability section in the
  root `README.md` and in each of the two service READMEs; and the OpenSpec project
  context in `openspec/config.yaml`, whose Components list described the repository
  as if history-service, eval-service, otel-lgtm and `dragncards-common` did not
  exist.
- **The agent context gains a concrete checklist.** A new *Adding or Changing a
  Service* section in the root `AGENTS.md` states, file by file, what must be
  wired and where — naming the code-level telemetry steps specifically, because
  the failure mode was "env vars set, tracer never initialised", not "configured
  wrongly". It also records the standing rule that README, OpenTelemetry
  configuration, Docker/infrastructure configuration and the `Makefile`/`scripts/`
  entries are kept current by whatever change requires them. Both services were
  also missing from the root `AGENTS.md` *Service-Level Guides* and *Useful
  Reading* lists; both lists are corrected.

## Non-goals

- No new observability design. Parity with the existing pattern is the target;
  the exporters, endpoints, signal set and span granularity are the ones the
  working services already use.
- No migration of `game-service` onto the shared bootstrap, for the reason given
  above. It keeps its own equivalent copy and both `AGENTS.md` and the README say
  so, so the next person does not read the duplication as an accident and does not
  add a third copy.
- No change to the collector, the Grafana dashboards, or `docker-compose.infra.yaml`.
- The dashboard's Swagger index (`features/swagger/lib/openapi.ts`) loops over
  `["orchestrator", "game"]` only, so history-service and eval-service are absent
  from it. That is the same omission pattern but a different surface and it belongs
  to DRA-20; untouched here.
- Documenting the dev flow is DRA-24; untouched here beyond the Observability
  sections this change's own edits require.

## Capabilities

### New Capabilities

This change introduces no new capability. Exporting telemetry from a first-party
service is exactly what the existing `observability` capability describes; the
defect was that its requirements enumerated four services and silently excluded
two. The delta therefore extends existing requirements rather than declaring a new
area.

### Modified Capabilities

- **observability**: the services-emit-telemetry requirement now names
  `history-service` and `eval-service` alongside the others and requires the
  bootstrap to be wired in code rather than only configured; the HTTP, database
  and Valkey edge requirements extend to both services; a new requirement makes
  the shared bootstrap the single implementation for services that can use it and
  records `game-service`'s documented exception; a new requirement forbids
  request bodies, prompts, model responses, recorded game state and credentials as
  span attributes.

## Impact

- **Production code**:
  - `services/shared/src/dragncards_common/telemetry.py` (new — the shared bootstrap)
  - `services/shared/pyproject.toml` (OpenTelemetry SDK, exporters, instrumentation)
  - `services/history-service/src/history_service/telemetry.py` (new)
  - `services/history-service/src/history_service/{main.py,runtime/app.py,runtime/ingest.py,runtime/restore.py,runtime/snapshots.py,storage/db.py,storage/valkey.py}`
  - `services/eval-service/src/eval_service/telemetry.py` (new)
  - `services/eval-service/src/eval_service/{main.py,runtime/app.py,runtime/worker.py,storage/db.py}`
  - `services/agent-orchestrator/src/agent_orchestrator/telemetry.py` (reduced to a binding)
  - `services/agent-orchestrator/pyproject.toml` (OpenTelemetry now arrives via `dragncards-common`)
  - `services/dashboard/instrumentation.ts` (trace-context propagation to all four backends)
- **Tests**: `services/shared/tests/test_telemetry.py` (new),
  `services/history-service/tests/unit/test_telemetry.py` (new),
  `services/eval-service/tests/unit/test_telemetry.py` (new),
  `services/dashboard/features/observability/__tests__/instrumentation.test.ts` (new),
  `services/agent-orchestrator/tests/unit/test_telemetry.py` (rewritten against
  the binding), plus `OTEL_SDK_DISABLED=true` in the history-service and
  eval-service test root `conftest.py`.
- **Configuration**: `docker-compose.yaml`,
  `services/{game-service,agent-orchestrator,history-service,eval-service}/.env.example`.
- **Documentation**: `README.md`, `AGENTS.md`, `openspec/config.yaml`,
  `services/history-service/{README.md,AGENTS.md}`,
  `services/eval-service/{README.md,AGENTS.md}`.
- **Database**: none.

## Notes

End-to-end span delivery is **unverified**. Six sibling agents run concurrently on
this batch and would collide on ports, so no Docker stack was started and no
integration tests were run from this worktree. Everything here is verified by unit
test and by reading configuration. What the orchestrator should confirm after
merge is recorded in `tasks.md` section 8.
