# Replace wildcard browser CORS with a dashboard-origin allowlist

## Why

DRA-31 reports that `history-service` configures CORS as `allow_origins=["*"]` with
`allow_methods=["*"]`. `docker-compose.yaml` publishes 4004 on the host, so **any
web page a developer visits while the stack is running can issue a cross-origin
`DELETE http://localhost:4004/games/{game_id}`** and the browser will carry it out.
The event store is the only durable record of what an agent did, so that destroys
the evidence a debugging loop exists to read.

This was reproduced over the wire before any code changed. A foreign origin's
preflight for a `DELETE` was granted in full:

```
$ curl -isX OPTIONS http://127.0.0.1:4220/games/some-game \
    -H "Origin: https://evil.example" -H "Access-Control-Request-Method: DELETE"
HTTP/1.1 200 OK
access-control-allow-origin: *
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-max-age: 600
```

and the `DELETE` it clears then removed a recorded game outright — `{"game_id":
"victim-game","deleted_events":1,"deleted_snapshots":0}`, with `GET /games`
returning `{"games":[]}` after.

Three things make this worse than a lone misconfiguration.

**It defeats a control that already exists.** `isCrossSiteRequest` in
`services/dashboard/features/proxy/lib/proxy.ts` rejects `cross-site` and
`same-site` requests precisely so a foreign page cannot drive these services
through the dashboard. That check is worthless when a page can skip the proxy and
talk to 4004 directly.

**It undermines the MCP exclusions.** history-service's `EXCLUDED_ROUTES`
deliberately withholds `delete_game_history`, `backfill_game_event` and
`import_game_bundle` from a model because they destroy or forge the record.
Withholding them from an LLM while handing the same three operations to any page
in a browser makes the exclusion decorative.

**Two sibling services silently disagreed.** eval-service already carried a strict
configurable allowlist, with a comment explaining exactly why it is safe. Nothing
distinguished the two services' needs; history-service simply never got the same
treatment. So the fix is to adopt eval-service's shape rather than invent a third
policy.

Auditing all four services found the divergence was wider than the report:

| Service | Before | Deliberate? |
| --- | --- | --- |
| `eval-service` | `settings.cors_allow_origins`, default `http://localhost:3001,http://127.0.0.1:3001` | **Yes** — a comment explains that the dashboard uses a server-side proxy, so a strict list is safe |
| `history-service` | `["*"]` | No — no comment, no rationale |
| `game-service` | `["*"]` | No — the comment read "allow all origins for development; restrict in production", conceding it was a shortcut |
| `agent-orchestrator` | `["*"]` | No — no comment at all |

`game-service` and `agent-orchestrator` are wrong for the same reason and with
comparable consequences — `DELETE /games/{session_id}` on 4001, and
`DELETE /sessions/{id}` plus `POST /sessions/{id}/prompts` (which spends the
owner's model budget) on 4002 — so they are fixed here too. Fixing only
history-service would have left the attack substantially open while appearing
closed.

**Nothing legitimately reaches these services from a browser**, which is what makes
an allowlist safe rather than merely stricter. This was verified rather than
assumed:

- Every dashboard call goes through its own server-side proxy at relative
  `/api/proxy/<service>/...` URLs. `SERVICE_KEYS` in `proxy.ts` is the single
  declaration of the four services it fronts, and a grep for direct
  `localhost:400x` fetches in `services/dashboard` found none outside
  `dashboard-config.ts` (server-side base URLs) and the MCP URL handed to the
  orchestrator.
- The three `EventSource` call sites — `use-job-streaming.ts`,
  `subagent-list.tsx`, `subagent-output-modal.tsx` — all target
  `/api/proxy/orchestrator/jobs/{id}/events/stream`, not port 4002. The SSE feed
  is proxied like everything else.
- The proxied request therefore originates in the dashboard's Node process and
  carries **no `Origin` header**, so CORS does not apply to it at all. That proxy
  also strips `cookie` and `authorization` and rewrites `host`.
- The remaining callers are server-to-server (eval-service → history-service,
  history-service → game-service and the orchestrator) or MCP clients, which are
  not browsers.
- game-service's own `/docs` playground is same-origin, and CORS never applies to
  a same-origin request.

## What Changes

### Each service takes a configurable origin allowlist, defaulting to the dashboard

The policy is eval-service's, copied per service rather than abstracted, matching
the repo convention of following each service's own existing structure:

- `history-service` — `HISTORY_CORS_ALLOW_ORIGINS`, a `Field` with `AliasChoices`
  and a `cors_allow_origins` property on `Settings`, exactly like eval-service's.
- `agent-orchestrator` — `CORS_ALLOW_ORIGINS`, the same shape; the unprefixed name
  matches its own convention (`MAX_REQUEST_BODY_BYTES`, `CONTEXT_WINDOW_SIZE`).
- `game-service` — `CORS_ALLOW_ORIGINS`, read by a `cors_allow_origins()` helper in
  `api/app.py`. This service has no `Settings` class at all; `main.py` reads
  `os.environ` directly, and the helper follows that rather than introducing a
  settings layer for one value.
- `eval-service` — unchanged behaviour. Its default and parsing are already correct.

All four default to `http://localhost:3001,http://127.0.0.1:3001`, the dashboard's
browser origin, and none hardcodes a value that works on only one machine.

`allow_methods=["*"]` and `allow_headers=["*"]` are kept everywhere, unchanged and
matching eval-service. The origin allowlist is the control; narrowing methods as
well would add churn without adding protection, since a disallowed origin never
gets past the preflight regardless of the methods advertised.

### The measured effect

The same request that was granted above is now refused, with no
`access-control-allow-origin` for the browser to accept:

```
$ curl -isX OPTIONS http://127.0.0.1:4220/games/some-game \
    -H "Origin: https://evil.example" -H "Access-Control-Request-Method: DELETE"
HTTP/1.1 400 Bad Request
vary: Origin
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT

Disallowed CORS origin
```

Starlette still echoes `access-control-allow-methods` on a rejected preflight. That
header is inert on its own: a preflight without `access-control-allow-origin` fails
no matter what methods it advertises, so the browser never sends the `DELETE`.

The dashboard origin still gets its preflight, echoed explicitly rather than as
`*`, and a request with **no `Origin`** is untouched — same `200`, same body, and no
CORS headers added, because CORS does not apply to it. That last case is the one the
whole application depends on, and it is the most likely way a stricter policy breaks
things.

### What CORS does and does not achieve here

Recorded in the code, the READMEs and the service guides, because the limit is easy
to overstate: **CORS is a browser control, not authentication.** It stops a browser
being used as a confused deputy for methods that require a preflight — `DELETE`,
`PUT`, and `POST` with a JSON content type, which covers every destructive route
named above. It does nothing about a non-browser client: `curl`, a script, anything
that can reach the published port simply omits `Origin` and is unaffected. Requiring
a credential is DRA-32, deliberately separate because it needs product decisions.

### The policy is pinned by a test in each of the four services

A new `tests/unit/test_cors.py` per service asserts, against the **real app factory
over the wire** rather than by inspecting configuration:

- a foreign origin's preflight for each destructive route answers `400` with no
  `access-control-allow-origin`;
- a foreign origin gets no `access-control-allow-origin` on a simple `GET`, so a
  page cannot read the response;
- the dashboard origin still gets its preflight, echoed explicitly;
- a request with no `Origin` still succeeds and gains no CORS headers;
- the default allowlist contains the dashboard origins and never `*`;
- the env var parses a comma-separated list, trimming blanks.

The wire-level assertions are the point. A config-only test — which is all
eval-service had — passes happily while someone hardcodes `["*"]` back into the app
factory. This was proven, not assumed: reintroducing the wildcard in all four
factories fails 5 tests in history-service, 4 in agent-orchestrator, and 3 each in
game-service and eval-service.

eval-service gains the same test file even though its behaviour does not change,
closing the same gap in the one service that was already correct.

## Non-goals

- **Authentication or authorization of any kind.** That is DRA-32, kept separate
  because it needs product decisions from the owner about what credential these
  services carry.
- Changing what any endpoint does, its request or response shape, or its status
  codes. No route is added, removed, or altered.
- Changing the MCP `EXCLUDED_ROUTES` of any service. This change makes those
  exclusions meaningful over HTTP; it does not revisit which routes they cover.
- Narrowing `allow_methods` or `allow_headers`, or setting `allow_credentials`
  (which stays at its default of false, the stricter setting).
- Changing the dashboard proxy, including `isCrossSiteRequest`. The proxy is what
  makes an allowlist safe, and it is unchanged.
- Rejecting `*` as an operator-supplied value. An operator who deliberately sets
  the env var to `*` is making a choice; the tests pin the shipped default and the
  code, which is what regressed.
- Introducing a shared CORS helper in `dragncards_common`. Each service follows its
  own existing configuration structure, per the repo convention.
- Binding these services to loopback instead of publishing them, or otherwise
  changing the port layout.

## Impact

- Affected specs: `infrastructure` (a browser CORS allowlist required of all four
  first-party HTTP services, with the no-`Origin` path preserved).
- Affected code:
  - `services/history-service/src/history_service/config.py` and
    `runtime/app.py` — the `HISTORY_CORS_ALLOW_ORIGINS` setting, its
    `cors_allow_origins` property, and the middleware that consumes it.
  - `services/agent-orchestrator/src/agent_orchestrator/config.py` and
    `runtime/app.py` — the same for `CORS_ALLOW_ORIGINS`.
  - `services/game-service/src/game_service/api/app.py` — the
    `cors_allow_origins()` helper, `DEFAULT_CORS_ALLOW_ORIGINS`, and the
    middleware.
  - `services/{history-service,game-service,agent-orchestrator,eval-service}/tests/unit/test_cors.py`
    (new) — the wire-level policy pin, in all four.
- Configuration, kept current in the same change:
  - `docker-compose.yaml` — `CORS_ALLOW_ORIGINS` for game-service and
    agent-orchestrator, `HISTORY_CORS_ALLOW_ORIGINS` for history-service, and
    `EVAL_CORS_ALLOW_ORIGINS` for eval-service. Each is overridable from the
    environment. eval-service had read its variable since it shipped but it was
    never exposed here, so the Compose deployment could not configure it — fixed
    alongside.
  - `services/{history-service,game-service,agent-orchestrator}/.env.example` — the
    new variable with its default and a warning against `*`. eval-service's
    `.env.example` already documents its own.
- Documentation, kept current in the same change: a `Browser CORS` section in the
  `history-service`, `game-service` and `agent-orchestrator` READMEs and
  `AGENTS.md` guides; the history-service README's variable table; and a paragraph
  in the root `README.md` under `MCP surfaces`, where the exclusion rationale that
  this change completes already lives.
- No database migration, no dependency change, no Dockerfile change, and no new
  service. `scripts/` and the `Makefile` enumerate services but not their
  environment variables, so neither needs an edit.
- Behaviour change a caller could notice: a browser page on an origin outside the
  allowlist can no longer read responses from, or send preflighted requests to,
  ports 4001, 4002 and 4004. No first-party caller is in that class. A developer
  who deliberately drives a service from a browser console on some other origin
  must now add that origin to the service's allowlist; `curl` and every
  server-to-server caller are unaffected because they send no `Origin`.
