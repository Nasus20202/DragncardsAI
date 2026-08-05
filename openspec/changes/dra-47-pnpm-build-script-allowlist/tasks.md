## 1. Establish the facts

- [x] 1.1 Confirm the repository layout: no root `package.json`, no root
      `pnpm-workspace.yaml`, no `.npmrc`; `services/dashboard` and
      `services/smoketest` are independent pnpm projects.
- [x] 1.2 Confirm the pnpm major in use (`packageManager` pins 11.17.0, CI
      installs 11.17.0) and that `onlyBuiltDependencies` does not exist in the
      pnpm 11 distribution while `allowBuilds` does.
- [x] 1.3 Enumerate the dashboard's packages with build scripts empirically, by
      installing into a clean scratch copy with `allowBuilds` removed.
- [x] 1.4 Run the same enumeration for `services/smoketest` and record that it
      has no packages with build scripts.
- [x] 1.5 Check the checked-in dashboard map against the lockfile and identify
      `protobufjs` as stale (zero occurrences in `pnpm-lock.yaml`).
- [x] 1.6 Read the install scripts of `@scarf/scarf` and `core-js-pure` from the
      installed packages and record what each actually does.
- [x] 1.7 Measure the exit code of an install with unapproved build scripts,
      with and without `strictDepBuilds`, to establish whether the failure is
      loud or silent.

## 2. Record the approvals

- [x] 2.1 Reconcile `allowBuilds` in `services/dashboard/pnpm-workspace.yaml`:
      drop `protobufjs`, keep the five native addons as `true`, set
      `@scarf/scarf` and `core-js-pure` to `false`.
- [x] 2.2 Annotate each entry with the artifact it produces or the reason it is
      denied, and record the regeneration recipe in a comment.
- [x] 2.3 Pin `strictDepBuilds: true` in
      `services/dashboard/pnpm-workspace.yaml`.
- [x] 2.4 Pin `strictDepBuilds: true` in
      `services/smoketest/pnpm-workspace.yaml`, with a comment explaining why it
      carries no `allowBuilds` map.

## 3. Prove it from a cold start

- [x] 3.1 Install the dashboard into a scratch copy with the new configuration
      and a clean `node_modules`; confirm exit 0 and no ignored-builds report.
- [x] 3.2 Confirm the resulting tree has its native artifacts — 29 `.node` files
      including `sharp`, `unrs-resolver` and the three tree-sitter packages —
      and that `node_modules/.modules.yaml` records `ignoredBuilds: []` and
      `pendingBuilds: []`.
- [x] 3.3 Run `pnpm install --frozen-lockfile` in the worktree's own
      `services/dashboard` and `services/smoketest`, both of which start with no
      `node_modules`, and confirm exit 0.
- [x] 3.4 Confirm neither `pnpm-lock.yaml` changed.
- [x] 3.5 Run `pnpm build` in `services/dashboard` and confirm exit 0 with all
      11 routes generated.

## 4. Keep the ancillary files current

- [x] 4.1 Establish how CI installs and whether it would hit the gate; record
      that `.github/workflows/test.yaml` installs per project directory and that
      `services/dashboard/docker/Dockerfile` copies `pnpm-workspace.yaml` in
      both stages, so no change is needed there.
- [x] 4.2 Add a "Node dependencies and build-script approvals" subsection to the
      root `README.md` covering per-project install, why approvals are checked
      in rather than granted with `pnpm approve-builds`, and what to do on
      `ERR_PNPM_IGNORED_BUILDS`.

## 5. Validate

- [x] 5.1 `openspec validate --all` shows no new failure beyond the pre-existing
      `spec/typed-game-actions` one.
- [x] 5.2 `./scripts/lint.sh --fix` passes.
- [x] 5.3 `./scripts/test.sh unit` passes.
