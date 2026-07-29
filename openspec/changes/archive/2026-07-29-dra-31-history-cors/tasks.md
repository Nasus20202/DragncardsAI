## 1. Establish the defect over the wire, before changing anything

- [x] 1.1 Read all four services' CORS configuration and record what each allows:
      `history-service`, `game-service` and `agent-orchestrator` at
      `allow_origins=["*"]`; `eval-service` at `settings.cors_allow_origins`
      defaulting to the dashboard origins, with a comment explaining why a strict
      list is safe.
- [x] 1.2 Judge whether each wildcard looks deliberate. game-service's comment
      ("allow all origins for development; restrict in production") concedes it is a
      shortcut; history-service and agent-orchestrator carry no rationale at all;
      eval-service's strict list is the only one with a stated reason. Conclusion:
      one considered decision and three unconsidered defaults, not four policies.
- [x] 1.3 Start history-service from the worktree on a free high port (4220) against
      a scratch sqlite file with the stream ingester disabled, so nothing touches
      the owner's running stack, its Postgres, or its `history:ingest` consumer
      group.
- [x] 1.4 Record the real response headers for a foreign-origin `DELETE` preflight:
      `200 OK`, `access-control-allow-origin: *`,
      `access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT`.
      Do the same for a `POST` preflight on `/games/{id}/events`.
- [x] 1.5 Demonstrate the consequence rather than only the header: backfill an event
      into `victim-game`, then issue the cross-origin `DELETE` the preflight cleared,
      and confirm `{"deleted_events":1}` with `GET /games` returning `{"games":[]}`.

## 2. Confirm nothing legitimately calls these services from a browser

- [x] 2.1 Read `services/dashboard/features/proxy/lib/proxy.ts` and confirm
      `SERVICE_KEYS` is the single declaration of the four services the dashboard
      fronts, all reached at relative `/api/proxy/<service>/...` URLs.
- [x] 2.2 Grep `services/dashboard` for direct `localhost:400x` fetches and confirm
      the only hits are `dashboard-config.ts` (server-side base URLs) and the
      game-service MCP URL handed to the orchestrator — no browser-direct calls.
- [x] 2.3 Check every `EventSource` call site (`use-job-streaming.ts`,
      `subagent-list.tsx`, `subagent-output-modal.tsx`) and confirm all three target
      `/api/proxy/orchestrator/jobs/{id}/events/stream` rather than port 4002, so
      the SSE feed is proxied like everything else.
- [x] 2.4 Confirm the proxied request carries no `Origin` (it originates in the
      dashboard's Node process), and note that the proxy also strips `cookie` and
      `authorization` and rewrites `host`.
- [x] 2.5 Confirm the remaining callers are server-to-server (eval-service →
      history-service; history-service → game-service and the orchestrator) or MCP
      clients, none of which are browsers.
- [x] 2.6 Confirm game-service's own `/docs` playground is same-origin, which CORS
      never applies to, so an allowlist does not break it.
- [x] 2.7 Grep `external/` for anything calling game-service and confirm there is
      nothing — game-service is a client of the DragnCards backend, not the reverse.

## 3. Adopt eval-service's shape in the three wildcarded services

- [x] 3.1 `history-service`: add `history_cors_allow_origins`
      (`HISTORY_CORS_ALLOW_ORIGINS`) as a `Field` with `AliasChoices` plus a
      `cors_allow_origins` property, mirroring eval-service's `config.py`, and
      consume it in `runtime/app.py`.
- [x] 3.2 `agent-orchestrator`: add `cors_allow_origins_raw` (`CORS_ALLOW_ORIGINS`)
      and the matching property, using the unprefixed variable name its own
      convention already uses (`MAX_REQUEST_BODY_BYTES`, `CONTEXT_WINDOW_SIZE`), and
      consume it in `runtime/app.py`.
- [x] 3.3 `game-service`: add `DEFAULT_CORS_ALLOW_ORIGINS` and a
      `cors_allow_origins()` helper reading `CORS_ALLOW_ORIGINS` in `api/app.py`.
      This service has no `Settings` class — `main.py` reads `os.environ` directly —
      so follow that rather than introducing a settings layer for one value.
- [x] 3.4 Default all three to `http://localhost:3001,http://127.0.0.1:3001`, the
      same value eval-service already uses, so no machine-specific origin is
      hardcoded.
- [x] 3.5 Keep `allow_methods=["*"]` and `allow_headers=["*"]` unchanged in all
      four, matching eval-service: the origin allowlist is the control, and a
      disallowed origin fails the preflight regardless of the methods advertised.
- [x] 3.6 Leave `allow_credentials` at its default of false everywhere — the
      stricter setting — rather than introducing it.
- [x] 3.7 Leave eval-service's configuration alone. Its default and parsing are
      already correct, so changing them would be churn.
- [x] 3.8 Record in each service's code comment *why* the wildcard must not return,
      naming the published port and the specific destructive routes it exposes.

## 4. Pin the policy with a test that catches a revert

- [x] 4.1 Add `tests/unit/test_cors.py` to `history-service`, `game-service` and
      `agent-orchestrator`, driving the **real app factory over HTTP** via
      `httpx.ASGITransport` rather than inspecting middleware configuration.
- [x] 4.2 Add the same file to `eval-service`, whose policy was covered only at the
      config level, so an edit hardcoding `["*"]` into its app factory would have
      passed every test. All four now pin the policy the same way.
- [x] 4.3 Assert a foreign origin's preflight for each destructive route answers
      `400` with no `access-control-allow-origin` — history-service parameterised
      over `DELETE /games/{id}`, `POST /games/{id}/events` and `POST /import`; the
      orchestrator over `DELETE /sessions/{id}` and `POST /sessions/{id}/prompts`.
- [x] 4.4 Record in the test why `access-control-allow-methods` is deliberately not
      asserted absent: Starlette still echoes it on a rejected preflight, and it is
      inert without `access-control-allow-origin`.
- [x] 4.5 Assert a foreign origin gets no `access-control-allow-origin` on a simple
      `GET`, so a page cannot read the response.
- [x] 4.6 Assert the dashboard origin is still granted its preflight, with the header
      echoing that specific origin rather than `*`.
- [x] 4.7 Assert a request with **no** `Origin` still returns `200` with its normal
      body and gains no CORS headers — the path every real caller uses, and the most
      likely way a stricter policy breaks the application.
- [x] 4.8 Assert the default allowlist contains both dashboard origins and never
      `*`, and that the env var parses a comma-separated list while trimming
      whitespace and empty entries.
- [x] 4.9 Enter no lifespan in these tests: CORS is middleware ahead of routing, and
      the only routed endpoint used is `/health`, which needs no database.
- [x] 4.10 Prove the tests catch the regression by reintroducing
      `allow_origins=["*"]` in all four app factories and confirming failures — 5 in
      history-service, 4 in agent-orchestrator, 3 each in game-service and
      eval-service — then restore the fix.

## 5. Verify the change over the wire

- [x] 5.1 Restart history-service on port 4220 from the fixed source and re-issue the
      identical foreign-origin `DELETE` preflight; record `400 Bad Request` with
      `Disallowed CORS origin` and no `access-control-allow-origin`.
- [x] 5.2 Confirm the destructive `DELETE` itself no longer carries
      `access-control-allow-origin`, so a browser could not read it even if it sent
      it — and that the preflight refusal is what stops it being sent at all.
- [x] 5.3 Confirm the dashboard origin's preflight is still granted, with
      `access-control-allow-origin: http://localhost:3001` echoed explicitly.
- [x] 5.4 Confirm the no-`Origin` request is unchanged from before the fix: same
      status, same body, no CORS headers.
- [x] 5.5 Confirm a foreign-origin simple `GET` is stripped of
      `access-control-allow-origin` relative to the before-fix capture.
- [x] 5.6 Stop the port-4220 server and confirm the port is free, having never bound
      4004 or run any `docker compose` or `scripts/docker*.sh` command against the
      owner's stack.

## 6. Keep the surrounding files current

- [x] 6.1 `docker-compose.yaml`: pass `CORS_ALLOW_ORIGINS` to game-service and
      agent-orchestrator and `HISTORY_CORS_ALLOW_ORIGINS` to history-service, each
      overridable from the environment with the dashboard default.
- [x] 6.2 `docker-compose.yaml`: also pass `EVAL_CORS_ALLOW_ORIGINS`. eval-service
      has read this setting since it shipped, but it was never exposed in Compose, so
      the containerised deployment could not configure it.
- [x] 6.3 Add the variable to `services/{history-service,game-service,agent-orchestrator}/.env.example`
      with its default and a warning against `*`. eval-service's already documents
      its own.
- [x] 6.4 Add a `Browser CORS` section to the `history-service`, `game-service` and
      `agent-orchestrator` READMEs, and the new variable to history-service's
      environment table.
- [x] 6.5 Add a `Browser CORS` section to the `history-service`, `game-service` and
      `agent-orchestrator` `AGENTS.md` guides, each stating the two invariants a
      future editor must not break: a no-`Origin` request must keep working, and CORS
      is not authentication.
- [x] 6.6 Add a paragraph to the root `README.md` under `MCP surfaces`, where the
      rationale for withholding destructive routes from MCP already lives, since this
      change is what makes that exclusion meaningful over HTTP.
- [x] 6.7 Confirm nothing else goes stale: `scripts/service-helpers.sh`,
      `scripts/lint.sh` and the `Makefile` enumerate services but not their
      environment variables; no Dockerfile, migration, dependency, or telemetry
      wiring is affected; no service is added or removed, so the dashboard's
      `SERVICE_KEYS` and the Swagger index are untouched.

## 7. Checks

- [x] 7.1 `./scripts/lint.sh --fix` then `./scripts/lint.sh` exits 0.
- [x] 7.2 `./scripts/test.sh unit` — report counts before and after.
- [x] 7.3 `./scripts/test.sh integration history-service` against throwaway
      `*_test_<uuid>` databases, safe alongside the owner's running instance.
- [x] 7.4 `openspec validate dra-31-history-cors --strict`.
- [x] 7.5 `openspec validate --all` — exactly one failure, the pre-existing
      `spec/typed-game-actions`.
- [x] 7.6 Grep the change directory for placeholder text (`TBD`, `TODO`, `???`,
      `FIXME`, `XXX`, "to be decided", "update after archive") and confirm none.
