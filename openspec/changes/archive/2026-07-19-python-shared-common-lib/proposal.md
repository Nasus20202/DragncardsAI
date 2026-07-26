# Shared internal Python library for backend services

## Why

The backend Python services (`agent-orchestrator`, `eval-service`,
`history-service`, `game-service`) each carried their own copy of the same
infrastructure code, drifting apart over time:

- The **schema-migration runner** (dialect-aware SQL loading, the
  `schema_migrations` ledger, applied-version bookkeeping) is ~99% byte-identical
  across three services; the only difference was a cosmetic one-line vs two-line
  `INSERT`.
- The **RESP / Valkey client** wire codec is duplicated in `agent-orchestrator`
  and `history-service`, and the copies diverged — the agent-orchestrator copy
  had a real bug: its RESP `-` (error) branch was dead code placed after a
  `return`, so `-ERR` replies were silently swallowed instead of raised.
- The **Bifrost gateway** typed error (`BifrostError`), the error-message
  extractor, and the timeout/network/gateway status mapping are byte-identical
  between `agent-orchestrator` and `eval-service`.
- The **lazy `httpx.AsyncClient` lifecycle** (`_http()` / `aclose()` /
  `health()`) is copy-pasted across four internal HTTP clients.

There was no shared-library mechanism in the monorepo, so every fix or
improvement had to be applied N times (and the RESP bug shows what happens when
it is not).

## What Changes

- **New internal package `dragncards-common`** at `services/shared/`
  (import name `dragncards_common`), a hatchling wheel consumed by other
  services via a uv path source (`{ path = "../shared", editable = true }`).
- **Migration runner** — extract `discover_migrations(sql_dir)` and
  `ensure_schema(engine, sql_dir, migrations)` into the shared package,
  parameterised on the SQL directory. Each service keeps its own
  `schema_migrations/sql/*.sql` and a thin `runner.py` that delegates while still
  exposing `MIGRATIONS` / `ensure_schema(engine)` so existing imports keep
  working. Adopted in `agent-orchestrator`, `eval-service`, `history-service`.
- **RESP client** — extract a single `RespConnection` (plus `RespError`) that
  handles the `-` error prefix CORRECTLY (fixing the agent-orchestrator bug),
  makes OpenTelemetry tracing OPTIONAL (soft/opt-in, so tracing-free consumers
  do not depend on otel), and includes `from_url()`. Adopted in
  `agent-orchestrator` (thin subclass wiring its tracer) and `history-service`.
  `game-service`'s private `_RespConnection` is intentionally left as-is (its
  span uses a different name and `start_as_current_span` semantics; adoption
  would change behavior).
- **Bifrost errors** — extract shared `BifrostError`, `extract_error_message`,
  and error-mapping helpers (`gateway_error`, `transport_error`) and adopt in
  both bifrost clients.
- **HTTP client base** — extract `BaseAsyncClient` (lazy `_http` / `aclose` /
  `health` + timeout) and have the four lazy-lifecycle clients inherit it. The
  agent-orchestrator `BifrostClient` adopts the shared error types but keeps its
  eager client lifecycle (migrating it would change construction timing).
- Consuming service `pyproject.toml` files gain the dependency + uv path source;
  their `docker/Dockerfile`s `COPY services/shared` before `uv sync`; and
  `scripts/lint.sh` formats the new package.

## Impact

- Affected specs: `infrastructure` (ADDED "Shared internal Python library").
- Affected code: new `services/shared/`; `schema_migrations/runner.py`,
  `storage/valkey.py`, and bifrost/integration HTTP clients in
  `agent-orchestrator`, `eval-service`, `history-service`; their
  `pyproject.toml` + `docker/Dockerfile`; `scripts/lint.sh`.
- Behavior change: the RESP `-ERR` reply is now surfaced as a `RespError` in
  agent-orchestrator (bug fix). No API or database-schema changes.
- The history envelope publisher / idempotency keys are deliberately NOT touched.
