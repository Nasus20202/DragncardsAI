# Tasks

## 1. Confirm the cause before changing anything

- [x] 1.1 Confirm `buildMergedOpenApi` looped a literal
      `["orchestrator", "game"] as const`, so no other service's document was ever
      fetched.
- [x] 1.2 Confirm the second site: `fetchOpenApiDocument` chose both the OpenAPI path
      and the base URL with a two-way `service === "orchestrator"` branch, so fixing
      only the loop would have merged game-service's document under the `history` and
      `eval` prefixes instead of erroring.
- [x] 1.3 Confirm `history` and `eval` were already valid `ServiceKey`s with
      `SERVICE_PREFIX` entries in the same file and working proxy routes — the bug was
      an incomplete list, not an unsupported service.
- [x] 1.4 Confirm each service really serves a document rather than adding an index
      entry that 404s: all four are FastAPI apps with no `openapi_url` override, and
      `GET /openapi.json` returns OpenAPI 3.1.0 for game-service (47 paths),
      agent-orchestrator (27), history-service (7) and eval-service (9).

## 2. One declaration of the service set

- [x] 2.1 Add `SERVICE_KEYS` to `features/proxy/lib/proxy.ts` and derive `ServiceKey`
      from it, so the type and the iterable set can never disagree.
- [x] 2.2 Rewrite `isServiceKey` as membership of `SERVICE_KEYS`.
- [x] 2.3 Add `getServiceBaseUrl` as a `Record<ServiceKey, string>` and use it from
      `resolveProxyUrl`, replacing the four-way ternary chain a fifth service would
      have fallen through.
- [x] 2.4 Add `getServiceProxyPrefix`, deriving the prefix from the key because it is
      the `[service]` segment of the `/api/proxy/[service]/[...path]` route, and delete
      the hand-written `SERVICE_PREFIX` map.
- [x] 2.5 Document on `SERVICE_KEYS` that a second list of services must never be
      written beside it, naming the failure it caused.

## 3. Merge every service

- [x] 3.1 Replace the literal loop in `buildMergedOpenApi` with `SERVICE_KEYS`.
- [x] 3.2 Replace the branch in `fetchOpenApiDocument` with `resolveOpenApiUrl`, which
      indexes a `Record<ServiceKey, string>` of OpenAPI paths and `getServiceBaseUrl`,
      so an unconfigured service key is a compile error.
- [x] 3.3 Add `historyServiceOpenApiPath` and `evalServiceOpenApiPath` to
      `features/config/lib/dashboard-config.ts` (`HISTORY_SERVICE_OPENAPI_PATH`,
      `EVAL_SERVICE_OPENAPI_PATH`), defaulting to `/openapi.json` via a shared constant.
- [x] 3.4 Add both variables to `vitest.setup.ts`, which the config test asserts covers
      every variable the config module reads.
- [x] 3.5 Leave `swagger-workspace.tsx` untouched — the page keeps its look.

## 4. A guard that fails if a service is dropped again

- [x] 4.1 Add a Swagger test that, for every key in `SERVICE_KEYS`, asserts the merged
      document contains that service's path under `/{service}` and that the set of
      fetched URLs is exactly one document per service from that service's own base URL.
- [x] 4.2 Add a test that a per-service OpenAPI path override is honoured, covering the
      path half of the resolution as well as the host half.
- [x] 4.3 Add proxy tests that `SERVICE_KEYS` is exactly the four accepted keys and
      that every key resolves to its own distinct configured base URL.
- [x] 4.4 Update the two pre-existing Swagger tests to dispatch per service, so the
      error-collection test still asserts exactly one failing service.
- [x] 4.5 Prove the guard: restore the old `["orchestrator", "game"]` loop and confirm
      both new Swagger tests fail, then restore the fix.

## 5. The second copy of the same list

- [x] 5.1 Derive `instrumentation.ts`'s `FIRST_PARTY_BACKENDS` from `SERVICE_KEYS` —
      Docker service name via `getServiceLabel`, plus the host of each configured base
      URL — replacing the hand-written array that spelled the same four services twice
      and that revives the previously unused `getServiceLabel`.
- [x] 5.2 Drive `instrumentation.test.ts` from `SERVICE_KEYS` instead of its own literal
      four names, so it can actually catch a missing service.
- [x] 5.3 Confirm the derived list is a superset of the old one under both
      configurations: local defaults give the same eight entries, and Docker URLs give
      the service names plus their real `host:port` instead of dead `localhost` entries.

## 6. Review findings addressed

- [x] 6.1 Stop a `response.json()` `SyntaxError` from carrying a prefix of a non-JSON
      upstream body into the unauthenticated `x-dashboard-errors`.
- [x] 6.2 Drop the dead `...merged.components` spread in the merge accumulator, which
      shallow-copied the whole components map once per service to no effect.
- [x] 6.3 Hoist `getServiceProxyPrefix(service)` out of the per-path `.map`.
- [x] 6.4 Cut the rationale comments down to one place per fact; the DRA-20 story lives
      in `AGENTS.md` and on `SERVICE_KEYS`, not on every function that keys off it.
- [x] 6.5 Hoist the pinned-service-URL `beforeEach` in `proxy.test.ts` to file scope
      instead of a third copy, and drop the assertion that distinct pinned URLs are
      distinct.
- [x] 6.6 Keep `isServiceKey`'s `(SERVICE_KEYS as readonly string[]).includes(value)`
      form: it matches the established idiom in `features/play/lib/player-agents.ts`.

## 7. Agent context and documentation

- [x] 7.1 Add a *dashboard service set* item to the root `AGENTS.md`
      *Adding or Changing a Service* checklist, naming `proxy.ts`, `openapi.ts`,
      `dashboard-config.ts`, `vitest.setup.ts`, and DRA-20 as the worked example.
- [x] 7.2 Name `features/swagger/lib/openapi.ts` in the *Keep the Surrounding Files
      Current* Swagger bullet, which previously said only "Swagger / API index".
- [x] 7.3 Add a *Per-Service Lists* section to `services/dashboard/AGENTS.md`.
- [x] 7.4 Document the Swagger playground URL and the origin of its service set in
      `README.md`.

## 8. Verify

- [x] 8.1 `./scripts/lint.sh --fix`, then `./scripts/lint.sh`.
- [x] 8.2 `./scripts/test.sh unit` — 1736 tests before, 1740 after, all passing.
- [x] 8.3 `pnpm typecheck` in `services/dashboard`.
- [x] 8.4 Drive the running app: `GET /api/openapi` returns 90 paths across all four
      prefixes with no errors, the embedded Swagger UI lists the `history:*` and
      `eval:*` tag groups, and `GET /eval/evaluations` executed from the playground
      returns live data through `/api/proxy/eval/evaluations`.
- [x] 8.5 `openspec validate --all` (only the pre-existing `spec/typed-game-actions`
      failure remains).
