# Capability endpoint so a client can detect version skew before it sends anything

## Why

DRA-56 made every agent-orchestrator request body reject a field it does not
define (`extra="forbid"`). That check is performed by the server, so it fires
only when the server does not recognise a field — and only from a server that
already carries the check. The orchestrator that produced DRA-53 predates it and
will keep answering `200 OK` while discarding fields until it is rebuilt. DRA-56
weighed three options for the other direction and deliberately did not take this
one; it filed it as a follow-up with the reasoning quoted in the ticket.

A capability endpoint is the one option without that asymmetry. A client asks
the server what it supports before it sends anything, and even a server old
enough to lack the endpoint answers conclusively: a `404` on `/capabilities` is
itself the signal that the server predates the negotiation. Nothing else in the
repository can tell a client "this server is older than the field you are about
to send" ahead of the send.

The decisions, as picked:

- **Feature list, not a version string.** A version string invites clients to
  compare versions and encode "supports X since 1.4", which rots. A feature
  list is precise — but someone must remember to add to it, which is exactly the
  class of omission DRA-53 came from, so the list is **derived, not
  maintained**: it is computed from the service's own OpenAPI document at
  startup, one `verb:path` entry per documented route. Adding a route adds it to
  the list; removing a route stops advertising it; there is no list to forget.
- **All four services.** The asymmetry is not the orchestrator's alone — a
  current client talking to an old game-service, history-service or eval-service
  has the same silent-discard failure — so every first-party service answers
  `GET /capabilities` the same way. The derivation is shared in
  `dragncards_common.capabilities`; game-service, which predates the shared
  library and does not depend on it, keeps a local copy of the same expression
  the way it keeps its own telemetry and MCP bootstraps.
- **The dashboard consumer is deferred.** `unappliedSessionSettings` already
  detects a dropped setting after the fact and names the settings that did not
  stick; a pre-save capability check is a second mechanism in the dashboard, and
  whether it is worth one is a separate decision. The endpoint is the durable
  half either way, so it ships now and the dashboard half can be layered on when
  it is wanted.

## What Changes

### The four services answer `GET /capabilities`

Each of agent-orchestrator, game-service, eval-service and history-service
exposes `GET /capabilities` returning:

```json
{"service": "<name>", "version": "<semver>", "features": ["get:/sessions/{id}", "post:/sessions/{id}/prompts", ...]}
```

- `service` is the service's name — the same `DEFAULT_SERVICE_NAME` the
  telemetry bootstrap binds.
- `version` is the app's own version string — the FastAPI constructor's, which
  the OpenAPI document's `info.version` echoes, so the payload cannot describe a
  different version than the document the guard tests derive the list from.
- `features` is every documented route as `verb:path`, sorted, derived from the
  app's own OpenAPI document at startup.

### The structural guard prevents a forgotten feature

The omission class DRA-53 came from — a capability that exists but is never
advertised — is closed by construction, and then pinned by a test per service in
the same pattern DRA-56 used (`tests/unit/test_app_strict_request_bodies.py`
derives its assertion from the app's own OpenAPI document). Each service's
`tests/unit/test_capabilities.py` builds the app, reads `app.openapi()`, asserts
`GET /capabilities` answers `200`, and asserts the advertised feature list
covers every documented route exactly once — so a route added later without an
`operation_id`, or an endpoint that stops documenting itself, fails the suite
rather than silently drifting from the answer a client would get.

### The endpoint is not an MCP tool

`/capabilities` answers "which server am I talking to, and what does it
support" — the server's own state, the same class as the liveness and readiness
probes. It is therefore kept out of every MCP surface by the same mechanism the
probes use: `ALWAYS_EXCLUDED_ROUTES` in `dragncards_common.mcp` for the three
services on the shared bootstrap, and game-service's own `route_maps`. The HTTP
endpoint is untouched, so the client that needs the answer asks over HTTP before
it sends anything — the exact flow the endpoint exists for.

## Capabilities

### Modified Capabilities

- `agent-orchestrator` — `GET /capabilities` describes the service's supported
  surface, derived from the app's own OpenAPI document.
- `game-service` — `GET /capabilities` describes the service's supported
  surface, derived from the app's own OpenAPI document.
- `eval-service` — `GET /capabilities` describes the service's supported
  surface, derived from the app's own OpenAPI document.
- `history-event-store` — the history-service answers `GET /capabilities` the
  same way.
- `service-mcp-surface` — the capability-negotiation endpoint is excluded from
  every service's MCP surface, like the probes.

## Impact

- **agent-orchestrator** — `api/routers/meta.py` gains the route;
  `tests/unit/test_capabilities.py` is new; `test_mcp_server.py` asserts the
  exclusion.
- **game-service** — `api/routers/meta.py` gains the route with a local copy of
  the derivation (the service does not depend on `dragncards-common`);
  `mcp/server.py` excludes it; `tests/unit/test_capabilities.py` and the MCP
  exclusion test are new.
- **eval-service** — `api/routers/meta.py` gains the route;
  `tests/unit/test_capabilities.py` is new.
- **history-service** — `api/routers/meta.py` gains the route;
  `tests/unit/test_capabilities.py` is new.
- **dashboard** — none. Whether a pre-save capability check is worth a second
  mechanism beside `unappliedSessionSettings` is a separate decision.
- **dragncards-common** — `capabilities.py` is new (the shared derivation);
  `mcp.ALWAYS_EXCLUDED_ROUTES` grows the `/capabilities` pattern; the shared MCP
  test asserts the exclusion.

## Non-goals

- **No version-string comparison.** A feature list, not a version, and no
  "supports X since" encoding anywhere in a client.
- **No dashboard consumer yet.** `unappliedSessionSettings` stays the only
  dashboard mechanism; a pre-save warning is a separate decision and is not
  built here.
- **No change to what a server does with an unknown field.** This is
  complementary to DRA-56, not a replacement: a server that knows the field
  still refuses it, and a client that asks first never sends it.
- **No hand-maintained feature list anywhere.** The list is derived from the
  OpenAPI document in the endpoint and in the tests; a literal list in source is
  the defect this change exists to prevent.
