# Tasks

## 1. Diagnose before fixing

- [x] 1.1 Confirm `docker-compose.yaml` already sets `OTEL_SERVICE_NAME`,
      `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_EXPORTER_OTLP_PROTOCOL` and
      `OTEL_RESOURCE_ATTRIBUTES` for history-service and eval-service, so the
      configuration side is not the cause.
- [x] 1.2 Grep `services/{history,eval}-service/{src,docker,pyproject.toml}` for
      `instrument|tracer|opentelemetry|otel`: zero hits each, against 49 for
      `game-service/src` and 63 for `agent-orchestrator/src`. The instrumentation
      was never written.
- [x] 1.3 Enumerate the specific gaps: no OpenTelemetry packages, no telemetry
      module (so global no-op providers stay installed), no `setup_telemetry()` in
      the entrypoint, no `instrument_app`, no SQLAlchemy instrumentation, and — for
      history-service — a Valkey client re-exported without a tracer, leaving the
      shared client's span code dormant.
- [x] 1.4 Confirm the `observability` spec named only `game-service`,
      `agent-orchestrator`, `dashboard` and Bifrost, which is why nothing flagged
      the omission.
- [x] 1.5 Confirm `dragncards_common` did NOT already offer a telemetry helper:
      the bootstrap existed as two byte-identical copies inside `game-service` and
      `agent-orchestrator`.
- [x] 1.6 Confirm the working services' manual spans carry only IDs and statuses,
      so there is no leaking pattern to inherit and copy.

## 2. Shared bootstrap in dragncards-common

- [x] 2.1 Add `dragncards_common/telemetry.py`: `TelemetryConfig.from_env`,
      `TelemetryRuntime`, `build_signal_endpoint`, `setup_telemetry`,
      `instrument_fastapi_app`, `instrument_sqlalchemy_engine`,
      `shutdown_telemetry`, `get_tracer` — behaviour identical to the copies it
      replaces, with `default_service_name` now a required argument.
- [x] 2.2 Import the FastAPI and SQLAlchemy instrumentors lazily behind
      `_fastapi_instrumentor()` / `_sqlalchemy_instrumentor()` so the shared
      library does not gain a dependency on either framework, and tests get one
      seam to stub.
- [x] 2.3 Declare the OpenTelemetry SDK, OTLP/HTTP exporters and the
      FastAPI/httpx/SQLAlchemy instrumentation in `services/shared/pyproject.toml`
      so a consuming service needs nothing but `dragncards-common`.
- [x] 2.4 Cover it in `services/shared/tests/test_telemetry.py`: env defaults and
      overrides, endpoint suffixing, the `OTEL_SDK_DISABLED` no-op building no
      exporter at all, all three signals wired with the right service identity,
      idempotency, both instrument helpers (once-only and skipped-when-disabled),
      and shutdown flushing every provider.

## 3. history-service wiring

- [x] 3.1 Add `history_service/telemetry.py` binding
      `DEFAULT_SERVICE_NAME = "history-service"` to the shared bootstrap.
- [x] 3.2 Call `setup_telemetry()` in `main.py` before the app is built.
- [x] 3.3 Call `instrument_fastapi_app(app)` in `runtime/app.py` and
      `shutdown_telemetry()` in the lifespan teardown.
- [x] 3.4 Instrument the engine inside `storage/db.create_engine`.
- [x] 3.5 Subclass the shared `RespConnection` in `storage/valkey.py` to inject
      this service's tracer, mirroring the agent-orchestrator, so `valkey.execute`
      spans are actually emitted.
- [x] 3.6 Add manual spans: `history.ingest_batch` (per polled batch, recording
      `history.events_processed`), `history.take_snapshot`, and `history.restore`
      via a thin traced wrapper over the existing workflow.
- [x] 3.7 Set `OTEL_SDK_DISABLED=true` in `tests/conftest.py` so the suite starts
      no exporters.

## 4. eval-service wiring

- [x] 4.1 Add `eval_service/telemetry.py` binding
      `DEFAULT_SERVICE_NAME = "eval-service"` to the shared bootstrap.
- [x] 4.2 Call `setup_telemetry()` in `main.py` before the app is built.
- [x] 4.3 Call `instrument_fastapi_app(app)` in `runtime/app.py` and
      `shutdown_telemetry()` in the lifespan teardown.
- [x] 4.4 Instrument the engine inside `storage/db.create_engine`.
- [x] 4.5 Add one `eval.evaluate_target` span per graded target in
      `runtime/worker.py`, recording the outcome (`evaluated`, `not_configured`,
      `cancelled`, `failed`) and no further detail about a failure.
- [x] 4.6 Set `OTEL_SDK_DISABLED=true` in `tests/conftest.py`.

## 5. Remove the duplication rather than add to it

- [x] 5.1 Reduce `agent_orchestrator/telemetry.py` to a binding over the shared
      bootstrap, so this change does not leave a third identical copy.
- [x] 5.2 Drop the now-redundant OpenTelemetry entries from
      `agent-orchestrator/pyproject.toml`: they arrive with `dragncards-common`,
      and the service has no direct `opentelemetry` import left.
- [x] 5.3 Rewrite `agent-orchestrator/tests/unit/test_telemetry.py` against the
      binding — identity, entrypoint call, both edges, and the Valkey tracer —
      since the bootstrap internals it used to monkeypatch now live in the shared
      suite.
- [x] 5.4 Leave `game-service` on its own copy and say so in `AGENTS.md` and the
      README: it is the only Python service without a `dragncards-common`
      dependency and its image installs `uv sync --frozen` from its own lockfile,
      so migrating it needs a Dockerfile change no unit test can verify.

## 6. Do not turn telemetry into an exfiltration path

- [x] 6.1 Keep every new span attribute to identifiers, scopes, seqs, counts,
      mode flags and outcome words.
- [x] 6.2 Test the permitted attribute-key set for the history-service workflow
      spans, including that `history.take_snapshot` — which handles a full
      recorded game state — never puts that document on the span.
- [x] 6.3 Test that a judge failure whose gateway message embeds a bearer token
      and a prompt echo reaches the `eval.evaluate_target` span as the single
      outcome word `failed`, with the detail going to the target row through
      `sanitize_error_detail` instead.
- [x] 6.4 Keep all `.env.example` additions to commented placeholders; no key,
      token or connection secret in any committed file.

## 7. Ancillary files and agent context

- [x] 7.1 Add `depends_on: otel-lgtm (service_healthy)` for history-service and
      eval-service in `docker-compose.yaml`, matching the other three app
      services, and validate with `docker compose config`.
- [x] 7.2 Add the commented OpenTelemetry block to all four Python
      `.env.example` files — none of them had one, so fixing only the two new
      services would have left the new checklist item immediately false.
- [x] 7.3 Add an Observability section to the root `README.md` and to each of the
      two service READMEs, and correct the `dragncards-common` sentence to include
      the telemetry bootstrap.
- [x] 7.4 Add the *Adding or Changing a Service* section to the root `AGENTS.md`:
      the code-level telemetry steps named explicitly, the span-attribute
      prohibition, and the file-by-file list (compose, `.env.example`,
      `service-helpers.sh`, `lint.sh`, README, AGENTS.md, specs), plus the standing
      rule that README / OTel / Docker / `Makefile`-`scripts` are kept current by
      whatever change requires them.
- [x] 7.5 Add history-service and eval-service to the root `AGENTS.md`
      *Service-Level Guides* and *Useful Reading* lists, which had omitted both.
- [x] 7.6 Add an Observability section to each service's `AGENTS.md` naming the
      edges that must stay wired and the forbidden span attributes.
- [x] 7.7 Confirm `scripts/service-helpers.sh`, `scripts/lint.sh`, `scripts/run.sh`
      and the `Makefile` already enumerate both services — they do, so no change
      was needed there.
- [x] 7.8 Sweep every remaining file that names `agent-orchestrator` without
      naming `history-service`, to find the same omission elsewhere. Two live hits
      (the rest are archived changes and legitimately service-scoped specs):
      `services/dashboard/instrumentation.ts` and `openspec/config.yaml`.
- [x] 7.9 Fix the dashboard's `propagateContextUrls`: add `history-service`,
      `eval-service`, `localhost:4004` and `localhost:4005`, extract the list into
      an exported `propagateContextUrls()` helper, and assert its contents in
      `features/observability/__tests__/instrumentation.test.ts` so the next added
      backend cannot be forgotten silently.
- [x] 7.10 Add history-service, eval-service, otel-lgtm and `dragncards-common` to
      the `openspec/config.yaml` Components list, which described the repository as
      if none of them existed.
- [x] 7.8 Write the `observability` spec delta so the requirements name the two
      services and can no longer exclude a service by silence.

## 8. Verify

- [x] 8.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh`.
- [x] 8.2 `./scripts/test.sh unit` — Python suites 1026 → 1059 tests, all passing
      (shared 16→27, agent-orchestrator 322→327, history-service 100→109,
      eval-service 210→218, game-service 378 unchanged); dashboard 355 unchanged.
- [x] 8.3 Confirm the new tests FAIL without the production change, by stashing
      each service's `src/` and re-running: 6 of 9 fail for history-service, 5 of 8
      for eval-service.
- [x] 8.4 `openspec validate --all` — only the pre-existing
      `spec/typed-game-actions` failure remains.
- [x] 8.5 Grep this change directory for `TBD`, `TODO`, `???`, "to be decided"
      and empty sections: none.
- [ ] 8.6 **Orchestrator, after merge:** bring the stack up and confirm end-to-end
      delivery, which this worktree could not do. In Grafana at
      http://localhost:3004 expect `service.name` values `history-service` and
      `eval-service` to appear alongside the existing ones; a trace for
      `GET /health` on ports 4004 and 4005 with a `http_server_duration_milliseconds`
      metric family per service; `db_client_connections_usage` for both once they
      touch their databases; `valkey.execute` spans from history-service while the
      ingester polls; `history.ingest_batch` spans after a game is played; an
      `eval.evaluate_target` span after an evaluation is requested; and logs from
      both services in Loki carrying a non-zero `trace_id`. Then confirm no span
      attribute in either service's traces contains prompt text or game state.
