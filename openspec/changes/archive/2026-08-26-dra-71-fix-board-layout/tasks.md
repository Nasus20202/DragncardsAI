# Tasks

## 1. Prove and fix the coupled asset lifecycle

- [x] 1.1 Inspect the current local image creation times, running container mounts,
  plugin volume contents, and checked-out submodule commits; record the mismatch.
- [x] 1.2 Make the plugin artifact copier replace its JSON/TSV directories without
  deleting the named volume or any game database volume.
- [x] 1.3 Make normal full-stack and infrastructure start/restart rebuild and
  force-recreate the frontend, backend, and plugin as a coupled group.
- [x] 1.4 Preserve the registry image path and the existing explicit `down-clean`
  behavior without making data deletion part of ordinary startup.

## 2. Regression checks and documentation

- [x] 2.1 Add Compose/lifecycle regression diagnostics and a live plugin-image to
  mounted-volume manifest comparison.
- [x] 2.2 Add the infrastructure test mode to `scripts/test.sh`.
- [x] 2.3 Document the rebuild/recreate behavior, data-preservation guarantee, and
  focused regression command.
- [x] 2.4 Run lint, unit, infrastructure, integration, and OpenSpec validation;
  archive this change after the affected infrastructure spec is synchronized.

## 3. Rendering fallback decision

- [x] 3.1 Do not alter rendering code: the clean version-matched asset rebuild is
  the scoped first fix, and no source-level rendering change was required.
