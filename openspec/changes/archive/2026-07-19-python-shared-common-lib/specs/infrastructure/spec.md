## ADDED Requirements

### Requirement: Shared internal Python library

The repository SHALL provide a single internal Python package,
`dragncards-common` (import name `dragncards_common`), under `services/shared/`,
that houses cross-service infrastructure code (the SQL migration runner, the
RESP/Valkey client, the Bifrost gateway error types + mapping, and the lazy
`httpx.AsyncClient` base) so that this logic lives in exactly one place rather
than being copy-pasted between services. Backend Python services that need this
code SHALL depend on it via a uv path source and SHALL NOT keep a private copy of
the extracted logic. The package SHALL treat OpenTelemetry as an optional
(soft) import so that a consumer without OpenTelemetry does not acquire the
dependency.

#### Scenario: Consuming service resolves the shared package

- **WHEN** a consuming service (`agent-orchestrator`, `eval-service`, or
  `history-service`) runs `uv sync`
- **THEN** `dragncards-common` SHALL resolve from the `../shared` path source and
  `dragncards_common` SHALL be importable by that service

#### Scenario: Shared package is packaged into service images

- **WHEN** a consuming service's `docker/Dockerfile` is built from the repo-root
  build context
- **THEN** the Dockerfile SHALL `COPY services/shared` before `uv sync` so the
  path-source dependency resolves inside the image and `dragncards_common`
  imports succeed at runtime

#### Scenario: RESP error replies are surfaced

- **WHEN** the shared RESP client reads a reply beginning with the `-` (error)
  prefix
- **THEN** it SHALL raise a `RespError` carrying the error text rather than
  silently ignoring it
