## Why

DRA-47 reported that no `onlyBuiltDependencies` is configured anywhere in this
repository, so approval of dependency build scripts exists only as per-machine
state written by `pnpm approve-builds` — meaning a fresh clone would silently
link native packages without their artifacts. Testing for the current batch is
happening on a different computer, which is exactly that case.

Investigating it changed the picture in two ways, both of which matter for what
should actually be built.

**The setting was renamed.** This repository is on pnpm 11 (`packageManager`
pins `pnpm@11.17.0`; CI installs the same). In pnpm 11 `onlyBuiltDependencies`
no longer exists — it is `allowBuilds`, a map of package name to boolean rather
than an array. The string `onlyBuiltDependencies` does not appear anywhere in
the pnpm 11 distribution. A search for the pnpm 10 name therefore finds nothing
even when the approvals are present, which is what happened here:
`services/dashboard/pnpm-workspace.yaml` has carried an `allowBuilds` map since
the dashboard was first added.

**Ignored builds already fail loudly, but only by default.** pnpm 11 defaults
`strictDepBuilds` to true, which turns an unapproved build script into
`ERR_PNPM_IGNORED_BUILDS` and a non-zero exit. Measured on a clean
`node_modules` with the allowlist emptied, `pnpm install --frozen-lockfile`
exits **1**; with `strictDepBuilds: false` the same install prints a warning box
and exits **0**, leaving the native packages unbuilt. So the silent-skip failure
mode the issue describes is real, but it is reached through configuration rather
than through the absence of an allowlist — and the repository pins nothing, so a
machine-level pnpm config setting `strictDepBuilds: false` would restore it on
precisely the fresh machine the issue is worried about.

The residual gaps are therefore narrower than reported, and different: nothing
pins the strict behaviour, the checked-in allowlist has drifted from the
dependency tree, and two of its entries grant install-time code execution to
packages that build nothing.

## What Changes

- `services/dashboard/pnpm-workspace.yaml` pins `strictDepBuilds: true`, so an
  unapproved build script is a hard install failure regardless of the pnpm
  default or a machine-level override.
- The dashboard's `allowBuilds` map is reconciled with the dependency tree,
  which was enumerated empirically by emptying the map and reading the packages
  pnpm then refused to build. The stale `protobufjs` entry is removed —
  `protobufjs` occurs zero times in `pnpm-lock.yaml`, so the entry stands as a
  standing pre-approval for a package that would run install scripts unreviewed
  if it ever re-entered the tree.
- `@scarf/scarf` and `core-js-pure` change from `true` to `false`. Neither
  produces a build artifact: `@scarf/scarf`'s postinstall is `node ./report.js`,
  which makes an HTTPS request to `scarf.sh` reporting install analytics, and
  `core-js-pure`'s is `node -e "try{require('./postinstall')}catch(e){}"`, a
  funding banner wrapped in a catch-all. Denying them removes install-time code
  execution and outbound network from two packages while keeping the install
  non-interactive and exit-0.
- The five genuine native addons — `sharp`, `unrs-resolver`, `tree-sitter`,
  `tree-sitter-json`, `@tree-sitter-grammars/tree-sitter-yaml` — stay `true`,
  each annotated with what it produces and which dependency pulls it in.
- `services/smoketest/pnpm-workspace.yaml` pins `strictDepBuilds: true`. No
  dependency in that project ships an install script today, so it gets no
  `allowBuilds` map; the setting exists so that one added later must be reviewed
  rather than skipped.
- The root `README.md` gains a "Node dependencies and build-script approvals"
  subsection stating that the two Node projects are installed separately, that
  approvals are checked in rather than granted with `pnpm approve-builds`, and
  what to do when an install stops with `ERR_PNPM_IGNORED_BUILDS`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `infrastructure`: the repository's Node projects declare which dependencies
  may execute install scripts, and treat an unapproved one as an install
  failure, so that a clone on any machine installs the same set without
  interactive approval.

## Non-goals

- Changing any dependency version or regenerating either lockfile. Both
  `pnpm-lock.yaml` files are byte-identical before and after this change.
- Removing `swagger-ui-react`, which is what drags the native `tree-sitter`
  parsers and `@scarf/scarf` into a Next.js dashboard. That the OpenAPI viewer
  costs three native addons is worth revisiting, but it is a dependency
  decision, not a build-approval one.
- Introducing a root `package.json` or a pnpm workspace spanning the two Node
  projects. They are independently installed by CI and by two different
  Dockerfiles, and merging them would change all of those call sites.
- Adding `.npmrc`. pnpm 11 reads these settings from `pnpm-workspace.yaml`, and
  a second config file would only create a place for them to disagree.
- Any change to the Python services, which use `uv` and are unaffected.

## Impact

- `services/dashboard/pnpm-workspace.yaml` — reconciled `allowBuilds`, pinned
  `strictDepBuilds`.
- `services/smoketest/pnpm-workspace.yaml` — pinned `strictDepBuilds`.
- `README.md` — contributor setup expectations for `pnpm install`.
- `openspec/specs/infrastructure/spec.md` — the new requirement, on archive.
- No CI change. `.github/workflows/test.yaml` already runs
  `pnpm install --frozen-lockfile` in each project directory, and
  `services/dashboard/docker/Dockerfile` already copies `pnpm-workspace.yaml`
  next to `package.json` and `pnpm-lock.yaml` in both its `deps` and `builder`
  stages. `services/smoketest` has no Dockerfile and is installed on the CI
  runner directly. Every install path therefore picks the pinned settings up as
  it stands.
