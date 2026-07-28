# Reach the Bifrost gateway UI from the dashboard navigation

## Why

Bifrost is the AI gateway every LLM call in the stack goes through, and it ships
its own web UI (host port 4003). While debugging a session — a provider that
will not list models, a request that never reached a provider, a virtual key
that is not wired up — the gateway's own view is the fastest place to look, but
the dashboard gives no way to get there. Today it means remembering the port and
typing `localhost:4003` by hand, or digging it out of `README.md`. The dashboard
already links every other part of the stack it can reach; the gateway is the
gap.

## What Changes

- **dashboard (application shell)** — the top navigation SHALL carry a `Bifrost`
  entry pointing at the Bifrost gateway UI. Because Bifrost is a separate
  application rather than a dashboard route, the entry SHALL open in a new
  browsing context (`target="_blank"` with `rel="noopener noreferrer"`) and SHALL
  be marked as leaving the dashboard, while rendering with the same typography,
  spacing, and hover treatment as the internal navigation entries. It is never
  the "active" entry, since no dashboard route corresponds to it.
- **dashboard (configuration)** — the gateway UI address SHALL come from a
  `BIFROST_UI_URL` environment variable, defaulting to `http://localhost:4003`,
  and SHALL be surfaced on the public dashboard configuration alongside
  `dragncardsFrontendUrl`. This is deliberately a *different* variable from the
  services' `BIFROST_URL`: that one is the Docker-internal
  `http://bifrost:8080`, which a browser on the host cannot resolve.
- Existing navigation behaviour is unchanged: `Play`, `Games`, `History`, and
  `Swagger` remain internal `next/link` routes with active-state highlighting.

## Non-goals

- Embedding the Bifrost UI in an iframe the way the DragnCards frontend is
  embedded. Bifrost is a third-party application with its own navigation and
  auth surface; a link keeps the boundary honest and avoids framing a tool we do
  not control.
- Proxying, authenticating, or health-checking the gateway UI from the
  dashboard. The link is unconditional — if Bifrost is not running the browser
  reports that, exactly as it would for any other service URL.
- Linking the remaining infrastructure UIs (Grafana on 3004, the DragnCards
  frontend on 3000). Adding those is a follow-up decision about how much of the
  stack belongs in the product navigation, not part of this change.

## Impact

- Affected specs: `dashboard` (Dashboard application shell; new Bifrost gateway
  UI link requirement).
- Affected code:
  `services/dashboard/features/shell/components/app-shell.tsx` (external nav
  entry), `services/dashboard/app/layout.tsx` (passes the URL through),
  `services/dashboard/features/config/lib/dashboard-config.ts` and
  `services/dashboard/features/shared/lib/types.ts` (`bifrostUiUrl` on the
  public config), `docker-compose.yaml` (dashboard `BIFROST_UI_URL`).
- New configuration variable `BIFROST_UI_URL`, optional with a working local
  default. No API or schema changes.
