# Design: version-match the DragnCards release unit

## Context

DragnCards has three coupled local artifacts:

1. the React frontend image, built from `external/dragncards/frontend`;
2. the Elixir backend image, built from `external/dragncards/backend`; and
3. the plugin artifact image, built from `external/dragncards-mc-plugin`, whose
   generated JSON and TSV files are copied into a named volume and mounted into
   the backend.

Compose dependency ordering only waits for the plugin container to complete. It
does not infer that a changed plugin image requires the already-created backend to
be recreated, and a completed one-shot container is not rerun merely because a
developer changed a submodule checkout. The old copy command also used
`cp -r /plugin/json /output/json`, which nests a new source directory when
`/output/json` already exists.

## Goals

- Make the ordinary local start path rebuild these three assets from the current
  checkout.
- Make the backend consume exactly the artifacts from the plugin image that was
  just built.
- Keep the fix safe for a developer's existing games and persistent engine state.
- Detect configuration regressions without requiring frontend rendering tests.

## Non-goals

- Changing card positioning, CSS, or any vendored rendering implementation.
- Replacing the persistent database or replay volumes.
- Introducing a version registry or publishing external images.

## Decisions

### Decision 1: Refresh the three external services as one unit

Both `scripts/docker.sh start` (the normal full-stack path) and
`scripts/docker-infrastructure.sh start|restart` build the local plugin, backend,
and frontend images unless `IMAGE_PULL_POLICY=always` selects the registry path.
They then force-recreate only those three services. The rest of infrastructure is
started through the existing derived service list.

This is deliberately a small explicit group rather than a build of every image on
every infrastructure restart. The frontend and backend are included even when
only the plugin submodule changed because the visible table and the backend's
plugin schema must be version matched.

**Alternative rejected: only add `--build` to `docker compose up`.** Compose can
rebuild the plugin image, but a dependency image change does not by itself force
recreation of the backend that mounts the named artifact volume. The backend could
therefore continue serving the previous plugin files.

**Alternative rejected: remove all volumes before starting.** That would hide the
stale-artifact issue by destroying user data and is not acceptable for a normal
developer workflow.

### Decision 2: Replace artifact directories in place

The plugin service removes `/output/json` and `/output/tsv`, creates them again, and
copies the contents of `/plugin/json` and `/plugin/tsv` using `/.`. This preserves
the named volume itself while making its artifact tree an exact copy of the image.
The backend still receives the volume read-only.

**Alternative rejected: `cp -r` into the existing directory.** It leaves old files
at the root and creates nested directories, allowing the backend to see a mixture
of releases.

### Decision 3: Test both wiring and the live artifact tree

`scripts/test.sh infrastructure` runs a focused script that checks the rendered
Compose graph, shared volume, copy command, root build contexts, and lifecycle
force-recreate wiring. When a backend container exists, it also compares sorted
SHA-256 manifests of `/plugin` in the plugin image and the mounted volume. When no
stack is running, the static checks pass and the live check reports a deliberate
skip.

The test does not create or remove persistent volumes. It reports a mismatch rather
than repairing it, so a stale deployment cannot silently pass validation.

## Risks and mitigations

- Recreating the three containers briefly interrupts the DragnCards table. The
  normal command already starts/stops infrastructure, and only the three coupled
  services are force-recreated; named database and engine volumes remain intact.
- Rebuilding external JavaScript and Rust sources costs startup time. It is bounded
  by the existing Docker build cache and is the reliable point at which checked-out
  submodule changes enter the stack.
- Registry startup must not build local source. `IMAGE_PULL_POLICY=always` skips
  local builds while still recreating the coupled services to refresh their shared
  artifact volume.
