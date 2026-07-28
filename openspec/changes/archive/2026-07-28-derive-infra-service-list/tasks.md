## 1. Fix the infrastructure helper

- [x] 1.1 Derive the service list in `scripts/docker-infrastructure.sh` from
      `docker-compose.infra.yaml` and `external/docker/docker-compose.yaml` via
      `docker compose config --services`, replacing the hardcoded string.
- [x] 1.2 Keep every action running through `docker compose -f docker-compose.yaml` so it
      targets the combined project, and `cd` to the repo root so the relative compose
      paths resolve regardless of the caller's working directory.
- [x] 1.3 Adopt `set -euo pipefail`, pass the services as a quoted array, send usage to
      stderr, and echo the resolved list for each action.

## 2. Audit the rest of the tooling

- [x] 2.1 Cross-check every hardcoded service name in `scripts/docker.sh`,
      `scripts/lint.sh`, `scripts/test.sh`, `scripts/run.sh`,
      `scripts/service-helpers.sh`, and `services/smoketest/smoke.sh` against
      `docker compose config --services` and the `services/` directory. No drift found:
      `lint.sh` and `service-helpers.sh` already cover `shared`, `history-service`, and
      `eval-service`, and the other scripts take services as arguments.
- [x] 2.2 Check that every action the `Makefile` passes to a script actually exists in that
      script's `case`. Found `make smoke-model` calling a nonexistent
      `services/smoketest/smoke.sh model` action; added the action and listed it in the
      script's usage string.
- [x] 2.3 Diff `Makefile` targets against `.PHONY` and against the `help` text; add the
      missing `smoke-test` phony entry.
- [x] 2.4 Correct `help` text that misstated behaviour (`down` removes containers; the
      `infra-*` scope).
- [x] 2.5 Verify the `README.md` service/port table against the compose defaults (all
      nine entries correct) and document the stack-lifecycle and `infra-*` targets.

## 3. Specs and verification

- [x] 3.1 Add an "Infrastructure-only lifecycle helper" requirement to
      `openspec/specs/infrastructure/spec.md`.
- [x] 3.2 Fix stale `docker-compose.yml` paths and the pinned `otel-lgtm` version in the
      same spec.
- [x] 3.3 Prove the derived list equals the compose project's services minus the five app
      services, without acting on the developer's running stack.
- [x] 3.4 `openspec validate --all`, `./scripts/lint.sh --fix`, and `./scripts/test.sh unit`
      pass.
