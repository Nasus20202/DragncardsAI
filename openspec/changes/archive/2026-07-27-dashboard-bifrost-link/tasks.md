## 1. Configuration

- [x] 1.1 Read `BIFROST_UI_URL` in `getServerConfig`, defaulting to
      `http://localhost:4003`, and expose it as `bifrostUiUrl` on the public
      dashboard configuration.
- [x] 1.2 Add `bifrostUiUrl` to the `DashboardConfig` type and to the existing
      configuration fixtures the dashboard tests build.
- [x] 1.3 Pass `BIFROST_UI_URL` to the dashboard container in
      `docker-compose.yaml`, documenting that it is the browser-reachable host
      address rather than the internal `BIFROST_URL`.

## 2. Navigation entry

- [x] 2.1 Extract the shared nav-entry class names in `AppShell` so an external
      entry cannot drift from the internal ones.
- [x] 2.2 Add an `ExternalNavLink` rendering a plain anchor with
      `target="_blank"`, `rel="noopener noreferrer"`, and an `aria-hidden`
      leaves-the-app marker; internal entries keep using `next/link`.
- [x] 2.3 Render a `Bifrost` entry after `Swagger`, fed by `bifrostUiUrl` from
      the root layout.

## 3. Tests

- [x] 3.1 Shell test: the Bifrost entry renders with the configured href,
      `target="_blank"`, `rel="noopener noreferrer"`, and the shared idle nav
      styling.
- [x] 3.2 Config test: `bifrostUiUrl` falls back to `http://localhost:4003` and
      honours `BIFROST_UI_URL` when set.
- [x] 3.3 `pnpm lint`, `pnpm typecheck`, `pnpm test`, and `pnpm build` pass in
      `services/dashboard/`; `./scripts/lint.sh --fix` passes at the repo root.
