## 1. Shared package scaffold

- [x] 1.1 Create `services/shared/` as `dragncards-common` (hatchling wheel,
      package `dragncards_common`, py314) with its own `pyproject.toml` and unit
      tests.
- [x] 1.2 Keep OpenTelemetry a SOFT/optional import so consumers without otel do
      not gain the dependency.

## 2. Migration runner

- [x] 2.1 Extract `discover_migrations(sql_dir)` + `ensure_schema(engine,
      sql_dir, migrations)` into `dragncards_common.schema_migrations`.
- [x] 2.2 Delegate each service's `schema_migrations/runner.py` to the shared
      runner while keeping `MIGRATIONS` / `ensure_schema(engine)` and the
      `storage/migrations.py` re-export shims.

## 3. RESP / Valkey client

- [x] 3.1 Extract `RespConnection` + `RespError` into `dragncards_common.resp`,
      handling the `-` error prefix correctly (fixing the AO dead-code bug) and
      making tracing optional; include `from_url()`.
- [x] 3.2 Adopt in agent-orchestrator (thin tracer-injecting subclass) and
      history-service (direct re-export). Leave game-service's `_RespConnection`
      as-is (documented, no-behavior-change constraint not met).

## 4. Bifrost errors + HTTP client base

- [x] 4.1 Extract `BifrostError`, `extract_error_message`, `gateway_error`,
      `transport_error` into `dragncards_common.bifrost`; adopt in both bifrost
      clients.
- [x] 4.2 Extract `BaseAsyncClient` into `dragncards_common.http_client`; have
      the four lazy-lifecycle clients inherit it. Keep AO `BifrostClient`'s eager
      lifecycle (adopt only its error types).

## 5. Packaging + tooling

- [x] 5.1 Add `dragncards-common` dependency + `[tool.uv.sources]` path source to
      the three consuming `pyproject.toml`s.
- [x] 5.2 `COPY services/shared` before `uv sync` in the three `docker/Dockerfile`s.
- [x] 5.3 Add `services/shared` to the `scripts/lint.sh` black loop.

## 6. Verification

- [x] 6.1 `uv sync` + unit tests pass for shared and all consuming services.
- [x] 6.2 `black` clean across shared + touched services.
- [x] 6.3 Docker image builds for history-service and imports `dragncards_common`.
