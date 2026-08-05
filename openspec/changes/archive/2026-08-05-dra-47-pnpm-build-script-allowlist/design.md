## Context

Two Node projects exist in this repository: `services/dashboard` (Next.js) and
`services/smoketest` (Playwright). There is no root `package.json`, no root
`pnpm-workspace.yaml`, and no `.npmrc`. Each project is installed independently
— by CI (`.github/workflows/test.yaml`, one step per project with
`working-directory` set), and for the dashboard also by
`services/dashboard/docker/Dockerfile`.

Both pin the same `packageManager` version, and CI installs the matching pnpm
via `pnpm/action-setup@v6`. All measurements below were taken with pnpm 11.17.0
(pnpm's `manage-package-manager-versions` resolves the pinned version
automatically) on Node 24, against clean `node_modules` directories in scratch
copies, so no concurrently running worktree was disturbed. The pin has since
moved to 11.20.0 with the routine dependency updates on `main`; `allowBuilds`
and `strictDepBuilds` are unchanged across those releases, and a
`pnpm install --frozen-lockfile` under 11.20.0 still exits 0 with no ignored
builds.

## Decisions

### D1: Record approvals in each project's `pnpm-workspace.yaml`

pnpm 11 reads `allowBuilds` and `strictDepBuilds` from `pnpm-workspace.yaml` at
the project root. Both projects already have that file (each currently carrying
`minimumReleaseAge: 0`), and the dashboard's is already copied into the Docker
build context, so the settings reach every install path without touching a
Dockerfile or a workflow.

Alternatives considered:

- **A root `pnpm-workspace.yaml` with `packages:`, making the repo one
  workspace.** Rejected: it would give the two projects a shared lockfile and a
  shared `node_modules`, which breaks the dashboard Dockerfile (it copies one
  project's lockfile into `/app`) and both CI install steps. That is a
  restructuring with its own risks, undertaken to relocate seven lines of
  configuration.
- **`pnpm.onlyBuiltDependencies` in each `package.json`.** Rejected: this key
  does not exist in pnpm 11. `onlyBuiltDependencies` appears nowhere in the
  pnpm 11 distribution, so it would be inert configuration that reads as
  protection.
- **An `.npmrc` per project.** Rejected: pnpm 11 has moved these settings to
  `pnpm-workspace.yaml`, and adding a second config file creates a second place
  to look and a way for the two to disagree.

### D2: Enumerate the packages with build scripts empirically, not from a list

The set was obtained by copying `package.json`, `pnpm-lock.yaml` and a
`pnpm-workspace.yaml` with no `allowBuilds` into a scratch directory and running
`pnpm install --frozen-lockfile` against an empty `node_modules`. pnpm then names
every package it refused to build. For the dashboard that is exactly eight:

| package | verdict |
| --- | --- |
| `sharp@0.34.5` | native, allowed |
| `unrs-resolver@1.12.2` | native, allowed |
| `tree-sitter@0.21.1` and `@0.22.4` | native, allowed |
| `tree-sitter-json@0.24.8` | native, allowed |
| `@tree-sitter-grammars/tree-sitter-yaml@0.7.1` | native, allowed |
| `@scarf/scarf@1.4.0` | telemetry, denied |
| `core-js-pure@3.49.0` | funding banner, denied |

For `services/smoketest` the same procedure reports **no** ignored builds at
all: `@playwright/test` downloads browsers through an explicit
`playwright install` step, not through a postinstall.

This mattered. The packages assumed at the outset to need approval —
`esbuild`, `lightningcss`, `@tailwindcss/oxide` — need none: current versions
ship per-platform prebuilt binaries as optional dependencies, which are plain
files pnpm links without running anything. Conversely `protobufjs` was allowed
in the checked-in map but occurs zero times in the lockfile. A guessed list
would have been wrong in both directions.

Alternatives considered:

- **Reading `requiresBuild` from the lockfile.** Rejected: the pnpm 11 lockfile
  format does not carry that field, and reconstructing it means unpacking every
  tarball in the store and reading its `scripts`. The install already computes
  the answer authoritatively.
- **`pnpm approve-builds`.** Rejected as the source of truth: it is interactive,
  and its purpose here is to write the file we are hand-authoring. It also
  cannot express a deny, which D3 depends on.

### D3: Deny build scripts that produce no artifact, rather than allowing them

`allowBuilds` is tri-state: `true` runs the script, `false` refuses it silently,
and absent means unreviewed — which under `strictDepBuilds` fails the install.
Two entries were verified by reading the installed package rather than by
reputation:

- `@scarf/scarf@1.4.0` declares `"postinstall": "node ./report.js"`. `report.js`
  builds an HTTPS request to `scarf.sh` carrying install analytics. It emits no
  file into `node_modules`. It arrives via `swagger-ui`, `swagger-ui-react` and
  `swagger-client`.
- `core-js-pure@3.49.0` declares
  `"postinstall": "node -e \"try{require('./postinstall')}catch(e){}\""` — a
  console funding banner, already written to tolerate its own failure.

Setting both to `false` narrows what may execute during an install without
changing what is installed. It is strictly better than omitting them, because an
omitted entry fails the install under D4 rather than expressing the decision.

The five native addons stay `true`. Each is a real compiled artifact reached
through `node-gyp-build`/prebuild selection, and denying one leaves a `require`
resolving to a missing `.node` at runtime — `sharp` behind Next.js image
optimisation, `unrs-resolver` behind `eslint-config-next`, and the three
tree-sitter packages behind the `@swagger-api/apidom-parser-adapter-json` and
`-yaml-1-2` parsers that `swagger-ui` uses.

Alternatives considered:

- **Leaving `@scarf/scarf` and `core-js-pure` at `true`.** Rejected: it grants
  install-time code execution, and in scarf's case an outbound network call from
  every developer machine and CI runner, for no build output.
- **`dangerouslyAllowAllBuilds`.** Rejected outright: it removes the boundary
  this change exists to sharpen.

### D4: Pin `strictDepBuilds: true` even though it is the pnpm 11 default

Measured with the allowlist emptied and a clean `node_modules`:
`pnpm install --frozen-lockfile` exits **1** with `ERR_PNPM_IGNORED_BUILDS` under
the default, and exits **0** with a warning box when `strictDepBuilds: false` is
set in `pnpm-workspace.yaml`. The second run also proves the setting is read
from that file rather than silently ignored.

pnpm resolves settings from global and user-level configuration as well as the
project's. A contributor or a CI image that has `strictDepBuilds=false` set
machine-wide would get the warning-and-continue behaviour — a fresh clone
linking native packages without their binaries, failing later as a missing
`.node`, which is the failure DRA-47 describes. A project-level setting takes
precedence, so pinning it removes that possibility and also survives a future
change of pnpm's default.

Alternative considered: **relying on the default.** Rejected because the whole
point of the change is that the guarantee must hold on a machine whose local
configuration we have never seen.

## Risks / Trade-offs

- **A dependency bump that adds an install script now breaks CI rather than
  degrading quietly.** This is intended, and it is the behaviour that was
  already in force by default; pinning it only makes it dependable. Renovate
  opens the bump as a PR, CI fails with the package named, and the reviewer
  makes the allow/deny call. The README documents that path.
- **Denying `@scarf/scarf` diverges from what its publisher expects.** scarf-js
  is designed to be disabled (it documents opting out) and cannot affect
  `swagger-ui`'s runtime behaviour, since nothing imports it at run time. The
  build was verified after the change: `next build` produced all 11 routes.
- **The allowlist can drift again**, as `protobufjs` did. `strictDepBuilds`
  catches an entry that is *missing*, but nothing fails when an entry becomes
  unnecessary. The mitigation is the regeneration recipe recorded in a comment
  at the top of the file, so the check is cheap for whoever next touches it.
- **Two versions of `tree-sitter` are in the tree** (0.21.1 and 0.22.4), each
  pulled by a different apidom adapter. `allowBuilds` keys on package name, so
  one entry covers both; no version-specific approval is possible or needed.
