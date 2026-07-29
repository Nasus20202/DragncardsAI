# Merge every first-party service into the Swagger index (DRA-20)

## Why

A user reported (DRA-20): *"http://localhost:3001/swagger is missing history, eval
services etc. Update agent context file to not miss it again."*

Confirmed, and the cause is two hardcoded two-service lists in one file —
`services/dashboard/features/swagger/lib/openapi.ts`.

**Site 1, the merge loop.** `buildMergedOpenApi` walked
`for (const service of ["orchestrator", "game"] as const)`. Only those two
documents were ever fetched, so history-service's 7 paths and eval-service's 9
paths could not appear in the index no matter how the rest of the file behaved.

**Site 2, the upstream resolution.** `fetchOpenApiDocument` chose both the OpenAPI
path and the base URL with a two-way branch:

```ts
const target = new URL(
  service === "orchestrator"
    ? config.orchestratorOpenApiPath
    : config.gameServiceOpenApiPath,
  service === "orchestrator" ? config.orchestratorUrl : config.gameServiceUrl
);
```

This is the more dangerous half. Fixing only the loop would have made `history`
and `eval` fetch **game-service's** document from **game-service's** host, and the
index would then have shown game-service's 47 endpoints three times under three
prefixes — a wrong index rather than an incomplete one, and no error to notice.
Neither `historyServiceOpenApiPath` nor `evalServiceOpenApiPath` existed in
`features/config/lib/dashboard-config.ts` at all.

**The bug was half-visible, which is why it survived.** `history` and `eval` were
already valid `ServiceKey`s, already had `SERVICE_PREFIX` entries in the very same
file, were already routable through `/api/proxy/[service]`, and already had
`resolveProxyUrl` tests. Every surface except the merge loop said the two services
were supported. `ServiceKey` was a hand-written union and the per-service maps were
hand-written lists beside it, so nothing made a partial list fail — not the type
checker, not a test, not the page (the merged document simply lacked those paths,
with an empty `x-dashboard-errors`).

Both services do serve a real document: each is a FastAPI app with no `openapi_url`
override, and `GET /openapi.json` returns OpenAPI 3.1.0 — "History Service" with 7
paths on port 4004, "Eval Service" with 9 paths on port 4005. There is no service
in the repository that needs an index entry it cannot serve.

The reporter's second sentence is the durable half. The root `AGENTS.md`
*Adding or Changing a Service* checklist (added by DRA-23) deliberately omitted the
Swagger index while the index itself was still broken, and *Keep the Surrounding
Files Current* mentioned "Swagger / API index" without naming a file — so an agent
adding a service had nothing concrete to check.

## What Changes

- **One declaration of the service set.** `SERVICE_KEYS` in
  `services/dashboard/features/proxy/lib/proxy.ts` becomes the single list, and
  `ServiceKey` is derived from it (`(typeof SERVICE_KEYS)[number]`) instead of being
  a parallel hand-written union. `isServiceKey` tests membership of that array.
- **The merge walks `SERVICE_KEYS`.** No literal list of service names remains in
  `openapi.ts`, so a service added to the declaration is merged without touching the
  Swagger feature.
- **Per-service resolution is exhaustive by type, not by branch.** The base URL moves
  into `getServiceBaseUrl` (a `Record<ServiceKey, string>`, replacing the four-way
  ternary chain `resolveProxyUrl` used), and the OpenAPI path becomes a
  `Record<ServiceKey, string>` in `openapi.ts`. Adding a key to `SERVICE_KEYS` without
  giving it a URL and a path is a compile error rather than a silent fall-through to
  another service's document.
- **The path prefix is derived from the key.** `getServiceProxyPrefix` returns
  `` `/${service}` ``, which is by definition the `[service]` segment of the
  `/api/proxy/[service]/[...path]` route, replacing the hand-written `SERVICE_PREFIX`
  map — one fewer list to keep in step.
- **history-service and eval-service get configurable OpenAPI paths.**
  `HISTORY_SERVICE_OPENAPI_PATH` and `EVAL_SERVICE_OPENAPI_PATH`, both defaulting to
  `/openapi.json` like the two that already existed, and both added to
  `vitest.setup.ts` so test isolation keeps covering every variable the config reads.
- **A regression guard driven by the declaration.** The Swagger test asserts, for
  every key in `SERVICE_KEYS`, that the merged document contains that service's path
  under that service's prefix **and** that it was fetched from that service's own
  base URL. Reintroducing either hardcoded list fails it — verified by restoring the
  old literal loop and watching the test fail.
- **The second copy of the same list is gone too.** `instrumentation.ts` hand-wrote
  `FIRST_PARTY_BACKENDS` — the same four services, spelled twice (Docker service name
  and `localhost:400x`) — and its test hardcoded the same four names, so neither could
  catch drift. It is now derived from `SERVICE_KEYS` via `getServiceLabel` and the host
  of each configured base URL, which also propagates trace context to the host the
  dashboard is actually configured to call rather than only to the two hardcoded
  spellings. This is the list whose incompleteness *was* DRA-23; leaving it literal
  while fixing the Swagger index would have left the same bug armed one file away.
- **The agent context names the file and the single declaration.** The
  *Adding or Changing a Service* checklist gains a dashboard-service-set item;
  *Keep the Surrounding Files Current* names `openapi.ts`; `services/dashboard/AGENTS.md`
  gains a *Per-Service Lists* section; and `README.md` documents the Swagger playground
  URL and where its service set comes from.
- **A parser message can no longer carry an upstream response body into the index.**
  `response.json()` failing on a 200 with a non-JSON body put a prefix of that body into
  `x-dashboard-errors` through the `SyntaxError` message, and that document is served
  unauthenticated. The parse now throws a fixed `"<service> OpenAPI document is not valid
  JSON"` instead.

## Non-goals

- **No restyling of the Swagger page.** `swagger-workspace.tsx` is untouched; the
  page keeps its Hero UI card, its `/api/proxy` chip, and its partial-load warning.
  The four services appear as additional tag groups inside the existing embedded
  Swagger UI.
- **No new dashboard route, tab, or navigation entry.** The index gained content, not
  chrome.
- **No change to proxy security behaviour.** Header stripping, cross-site rejection,
  and path-traversal rejection are untouched; `resolveProxyUrl` keeps its segment
  checks and only its base-URL lookup changed.
- **The merge stays sequential.** Four upstream fetches on a page load are not worth
  restructuring the error accumulation for.
- **No change to what the services publish.** All four already served OpenAPI 3.1.0
  at the framework default path; nothing in `history-service` or `eval-service` was
  modified.

## Capabilities

### New Capabilities

None. Merging service documents into one index is an existing dashboard capability
(*Merged Swagger playground*); this change corrects the set of services it covers and
the guarantee that the set cannot go stale, so the delta modifies existing
requirements rather than declaring a new area.

### Modified Capabilities

- **dashboard**: *Merged Swagger playground* now requires the index to cover **every**
  first-party service the dashboard proxies, each resolved against its own configured
  base URL and OpenAPI path, with the covered set derived from the single declaration
  the proxy route also uses. *Dashboard service configuration* now requires an OpenAPI
  source path per proxied service rather than for two named services.
- **observability**: *HTTP and runtime edges are instrumented across first-party services*
  now requires the dashboard's trace-context propagation targets to be derived from that
  same declaration, and its test to be driven by it, rather than both being hand-written
  lists of service names — plus propagation to a backend's configured host, not only its
  default one.

## Impact

- **Production code**:
  - `services/dashboard/features/proxy/lib/proxy.ts`
  - `services/dashboard/features/swagger/lib/openapi.ts`
  - `services/dashboard/features/config/lib/dashboard-config.ts`
  - `services/dashboard/instrumentation.ts`
- **Tests**: `services/dashboard/features/swagger/__tests__/openapi.test.ts`,
  `services/dashboard/features/proxy/__tests__/proxy.test.ts`,
  `services/dashboard/features/observability/__tests__/instrumentation.test.ts`,
  `services/dashboard/vitest.setup.ts`
- **Documentation**: `AGENTS.md`, `services/dashboard/AGENTS.md`, `README.md`
- **Configuration**: two new optional environment variables,
  `HISTORY_SERVICE_OPENAPI_PATH` and `EVAL_SERVICE_OPENAPI_PATH`. Neither is set in
  `docker-compose.yaml`, matching the two pre-existing `*_OPENAPI_PATH` variables,
  which are also defaults-only — so no infrastructure file changed.
- **Database**: none.

## Notes

- Left deliberately undone, each with the reason. **No authentication on the merged
  index or the proxy**: the playground now advertises unauthenticated state-changing
  endpoints it previously only *could* reach — `POST /eval/evaluations/clear`,
  `DELETE /history/games/{id}`, and `POST /eval/games/{id}/evaluations` with a
  caller-chosen judge model. No capability is new (the proxy already accepted both
  services, and `docker-compose.yaml` publishes 4004 and 4005 on the host directly), but
  the obscurity is gone, and closing it means adding a dashboard `middleware.ts` covering
  `/api/proxy/*`, `/api/openapi*` and `/swagger*` — a product decision, not part of
  completing an index. **No fetch timeout and no parallel merge**: four sequential
  fetches measured 20 ms warm end-to-end, so the throughput case is nil; the real
  argument is that one wedged upstream stalls `/swagger` for undici's 300 s default,
  which is a pre-existing gap this change makes twice as wide and which needs a
  deliberate timeout policy. **No absolute-URL rejection for `*_OPENAPI_PATH`**: an
  absolute or protocol-relative value overrides the base URL in `new URL(path, base)`,
  identically to the two variables that already existed; it requires control of the
  dashboard's environment, which already implies control of the base URLs.
  **`swagger-workspace.tsx` still fetches the whole merged document to read only
  `errors`**, so one page view builds it twice (once for the workspace, once for the
  embedded UI) — pre-existing waste this change doubled in fetch count, and fixing it
  means a new errors-only response shape.
- Verified end-to-end against the running stack with a dashboard dev server on port
  3021 pointed at the live services: `GET /api/openapi` returns 90 paths —
  `orchestrator` 27, `game` 47, `history` 7, `eval` 9 — with an empty
  `x-dashboard-errors`. The embedded Swagger UI renders 21 tag groups including
  `history:games`, `history:events`, `history:snapshots`, `history:restore`,
  `eval:evaluations` and `eval:meta`, and executing `GET /eval/evaluations` from the
  playground issued `http://localhost:3021/api/proxy/eval/evaluations?active=false&limit=50`
  and returned live eval-service data.
- Dead end worth recording: moving the per-service OpenAPI paths into a single record
  *inside* `dashboard-config.ts` typed as `Record<ServiceKey, string>` would be the
  tightest expression of "one declaration", but `proxy.ts` imports `getServerConfig`,
  so the config module cannot import `ServiceKey` back without a module cycle. The
  records therefore live at the two consumers, where the exhaustiveness check is
  equally strict.
