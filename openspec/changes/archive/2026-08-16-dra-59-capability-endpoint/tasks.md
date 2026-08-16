# Tasks

Ordered so the decision and the shared derivation settle before any service is
touched — all four services must answer identically, and game-service's local
copy must not drift from the shared one.

## 1. Settle the decision

- [x] 1.1 Weigh the feature list against a version string, and record the
      choice and the rejected alternative in `proposal.md` — a version invites
      "supports X since" encoding that rots; a feature list is precise and the
      omission risk is closed structurally.
- [x] 1.2 Decide the scope: one service or all four. All four carry the
      endpoint, because the silent-discard asymmetry exists on every service,
      and the derivation is shared where the shared library reaches.
- [x] 1.3 Decide the consumer question: the dashboard's pre-save capability
      check is a second mechanism beside `unappliedSessionSettings` and is
      deferred; the endpoint ships now.
- [x] 1.4 Record that a server old enough to lack the endpoint answers `404`,
      and that the `404` is itself the negotiation signal.

## 2. Share the derivation

- [x] 2.1 Add `dragncards_common/capabilities.py` with `route_features(openapi)`
      and `capabilities_payload(app, service_name)`, derived from the app's own
      OpenAPI document.
- [x] 2.2 Export it from `dragncards_common/__init__.py`.

## 3. Add the endpoint to all four services

- [x] 3.1 `agent-orchestrator` — `GET /capabilities` in `api/routers/meta.py`,
      using the shared payload builder.
- [x] 3.2 `eval-service` — `GET /capabilities` in `api/routers/meta.py`, using
      the shared payload builder.
- [x] 3.3 `history-service` — `GET /capabilities` in `api/routers/meta.py`,
      using the shared payload builder.
- [x] 3.4 `game-service` — `GET /capabilities` in `api/routers/meta.py`, with a
      local copy of the derivation (the service does not depend on
      `dragncards-common`).
- [x] 3.5 Every route carries an explicit `operation_id="capabilities"`.

## 4. Keep the endpoint out of MCP

- [x] 4.1 Add `^/capabilities$` to `ALWAYS_EXCLUDED_ROUTES` in
      `dragncards_common/mcp.py`, so the shared-bootstrap services exclude it
      with no per-service list entry.
- [x] 4.2 Exclude it in game-service's own `mcp/server.py` `route_maps`.
- [x] 4.3 Assert the exclusion in `services/shared/tests/test_mcp.py` and in
      each service's `test_mcp_server.py`, against the built surface rather than
      against the exclusion lists.

## 5. Pin the structural guard per service

- [x] 5.1 Add `tests/unit/test_capabilities.py` to each of the four services:
      build the app, read `app.openapi()`, assert `GET /capabilities` answers
      `200`, and assert the feature list covers every documented route exactly
      once — the DRA-56 derivation-against-the-document pattern.

## 6. Verify

- [x] 6.1 `./scripts/lint.sh` over the changed services.
- [x] 6.2 `cd services/agent-orchestrator && uv run pytest tests/unit/`.
- [x] 6.3 Run the new capabilities and MCP-surface tests in the other three
      services and the shared library.
- [x] 6.4 `openspec validate --all` — the single pre-existing failure on
      `spec/typed-game-actions` is the expected result.
- [x] 6.5 Archive the change with `openspec archive dra-59-capability-endpoint
      --yes` and confirm the archive directory exists.
