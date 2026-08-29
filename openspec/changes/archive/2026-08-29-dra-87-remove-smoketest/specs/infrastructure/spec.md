## REMOVED Requirements

### Requirement: Local smoke-model runtime wiring
The repository SHALL provide a documented local runtime path for a small `llama.cpp` model used by smoke tests, including the environment configuration needed for the dashboard and agent-orchestrator to target that model.

The smoke-model runtime SHALL remain optional for developers who are not running the smoke workflow.

#### Scenario: Smoke runtime can be started locally
- **WHEN** a developer follows the documented smoke-test setup for the local model runtime
- **THEN** the `llama.cpp` server SHALL be startable with the configured model artifact and reachable at the documented local endpoint

#### Scenario: Smoke runtime can be started through compose profile helper
- **WHEN** a developer runs the documented smoke helper or `make smoke-up` or `make smoke-model`
- **THEN** Docker Compose SHALL start the `llama-cpp-smoke-model-cache` and `llama-cpp-smoke` services under the optional `smoke` profile using the documented environment defaults

#### Scenario: Normal local stack does not require the smoke runtime
- **WHEN** a developer starts the normal local stack without the smoke-test workflow
- **THEN** the dashboard, game-service, and agent-orchestrator SHALL remain runnable without requiring the `llama.cpp` smoke-model process

## MODIFIED Requirements

### Requirement: Node dependency build scripts are approved in version control

The repository's Node projects SHALL declare in version control which
dependencies may execute install (build) scripts, and SHALL treat an
undeclared one as an install failure, so that installing on a machine that has
never seen this repository produces the same dependency tree as CI without any
interactive approval step.

`services/dashboard` is a standalone pnpm project:
there is no root `package.json` and no repository-wide pnpm workspace, and the
project is installed from its own directory. It SHALL carry its declaration in
its own `pnpm-workspace.yaml`, which is the file pnpm 11 reads these settings
from. The declaration SHALL NOT be recorded as `pnpm.onlyBuiltDependencies` in a
`package.json`: that key belongs to pnpm 10 and is absent from pnpm 11, so it
would be inert configuration that resembles protection.

Approval is expressed by the `allowBuilds` map, in which a package name mapped
to `true` may run its install script and a name mapped to `false` may not. A
package that has an install script and appears in neither state is unreviewed.
Each project SHALL set `strictDepBuilds: true`, which makes an unreviewed build
script fail the install rather than emit a warning. This is pnpm 11's default,
and it SHALL be pinned in the project anyway, because pnpm also resolves the
setting from user- and global-level configuration: a machine that disables it
would otherwise install a native package without its binary and report success,
deferring the failure to a missing `.node` file at run time.

A `true` entry grants a third-party package the right to execute arbitrary code
during every install, on every contributor machine and on every CI runner, so
the map SHALL be treated as a supply-chain boundary rather than a convenience
list. A package whose install script produces no artifact — install analytics,
a funding banner — SHALL be recorded as `false` rather than `true`, since
denying it costs nothing and leaves the decision stated. The set of packages
that need an entry SHALL be determined from the project's own dependency tree,
by emptying `allowBuilds` and reading the packages pnpm then refuses to build,
rather than copied from another project or assumed from a package's reputation.

Every install path SHALL pick these settings up without further configuration.
That holds for the CI workflow, which runs `pnpm install --frozen-lockfile` in
the project directory, and for the dashboard's Docker build, whose `deps` and
`builder` stages copy `pnpm-workspace.yaml` alongside `package.json` and
`pnpm-lock.yaml`.

#### Scenario: A clone with no prior pnpm state installs cleanly

- **WHEN** `pnpm install --frozen-lockfile` runs in `services/dashboard` against
  an empty `node_modules` on a machine where `pnpm approve-builds` has never
  been run for this repository
- **THEN** the install SHALL exit 0, SHALL NOT report any ignored build script,
  SHALL NOT prompt for approval, and SHALL leave `node_modules/.modules.yaml`
  recording no ignored and no pending builds

#### Scenario: Allowed native addons are actually built

- **WHEN** that install completes
- **THEN** the native artifacts of the allowed packages SHALL be present in
  `node_modules`, including those of `sharp`, `unrs-resolver`, `tree-sitter`,
  `tree-sitter-json` and `@tree-sitter-grammars/tree-sitter-yaml`
- **AND** `pnpm build` in `services/dashboard` SHALL exit 0

#### Scenario: An unreviewed build script fails the install

- **WHEN** a dependency that declares an install script is present in the tree
  and is named in neither the `true` nor the `false` state of `allowBuilds`
- **THEN** `pnpm install` SHALL fail with a non-zero exit code and SHALL name
  the offending package, rather than warning and linking it unbuilt

#### Scenario: A denied build script does not run and does not fail the install

- **WHEN** a package mapped to `false` — such as `@scarf/scarf`, whose
  postinstall reports install analytics over the network, or `core-js-pure`,
  whose postinstall prints a funding banner — is installed
- **THEN** its install script SHALL NOT run, and the install SHALL still exit 0
  without reporting it as ignored

#### Scenario: The approval list does not outlive the dependency

- **WHEN** a package named in `allowBuilds` is no longer present in the
  project's `pnpm-lock.yaml`
- **THEN** its entry SHALL be removed, so that the map never carries a standing
  pre-approval for a package that could re-enter the tree unreviewed

#### Scenario: A project with no build scripts still pins the strict setting

- **WHEN** a Node project has no dependency that declares an install script
- **THEN** it SHALL omit `allowBuilds` entirely and SHALL still set
  `strictDepBuilds: true`, so that a dependency which later introduces one is
  reviewed rather than skipped
