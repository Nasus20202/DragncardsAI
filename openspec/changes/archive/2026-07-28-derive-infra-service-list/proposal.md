# Derive the infrastructure service list so `infra-up/down/restart` cover every service

## Why

### `make infra-down` misses four services

`make infra-down` does not stop all infrastructure. `scripts/docker-infrastructure.sh`
carried a hardcoded list of eight service names:

```
dragncards-backend dragncards-frontend game-service-valkey agent-orchestrator-valkey
agent-orchestrator-postgres history-postgres eval-postgres bifrost
```

The compose project actually defines **twelve** infrastructure services. Four were
missing: `dragncards-postgres`, `dragncards-mc-plugin`, `otel-lgtm`, and
`lmstudio-proxy`.

The failure mode is asymmetric, which is why it went unnoticed for so long.
`docker compose up -d <subset>` also starts each subset member's `depends_on`
dependencies, so `infra-up` *did* bring up `dragncards-postgres` (needed by
`dragncards-backend`) and `otel-lgtm` + `lmstudio-proxy` (needed by `bifrost`).
`docker compose stop <subset>` has no such transitive behaviour — it stops exactly the
names given. So the script started twelve containers and stopped eight, silently
leaving three long-running containers (a PostgreSQL, the whole LGTM observability
stack, and the socat proxy) behind on every `make infra-down`.

The root cause is the hardcoded list itself: `eval-postgres`, `history-postgres`, and
`otel-lgtm` were all added to `docker-compose.infra.yaml` after the script was written,
and only some of them were ever back-ported into the string.

### `make smoke-model` is broken

Auditing the remaining scripts for the same class of drift turned up a second live bug.
`make smoke-model` runs `./services/smoketest/smoke.sh model`, but `smoke.sh` only ever
handled `up`, `check`, and `test` — `model` fell through to the usage branch and exited 1.
The target is advertised in `make help` and the `infrastructure` spec explicitly requires
it ("Smoke runtime can be started through compose profile helper" names `make smoke-model`
alongside `make smoke-up`), so the script had drifted away from both its own help text and
the spec.

## What Changes

- `scripts/docker-infrastructure.sh` **derives** its service list at runtime from the
  compose files that define infrastructure —
  `docker compose -f docker-compose.infra.yaml config --services` plus the same for
  `external/docker/docker-compose.yaml` — instead of hardcoding names. Adding a service
  to either file is now automatically covered.
- Actions still run through `docker compose -f docker-compose.yaml`, the file that
  `include:`s both infrastructure files, so they target the combined project the full
  stack runs under rather than a separate standalone project.
- The script gains `set -euo pipefail` (it had bare `set -e`), quotes the service list as
  an array instead of relying on word splitting, sends its usage message to stderr, and
  echoes the resolved service list so the scope of each action is visible.
- `services/smoketest/smoke.sh` gains the missing `model` action, which brings up
  `llama-cpp-smoke` under the `smoke` profile (its `service_completed_successfully`
  dependency pulls the model-cache download along), matching the first step the existing
  `up` action already performs. Its usage string now lists `model`.
- `Makefile`: `smoke-test` added to `.PHONY` (the target existed and was advertised in
  `help` but was not declared phony). `help` text corrected — `make down` removes
  containers rather than merely stopping them, and the `infra-*` lines now say what
  "infrastructure" means and that `infra-down` keeps containers.
- `README.md`: the Development section documents `make down` and the `infra-*` targets,
  and defines which services count as infrastructure versus application.
- `openspec/specs/infrastructure/spec.md`: stale `docker-compose.yml` paths corrected to
  `.yaml`, and the pinned `grafana/otel-lgtm:0.27.1` reference de-pinned (the compose file
  is on `0.29.2`; the spec should not carry a version that drifts on every bump).

## Non-goals

- Changing `infra-down` from `docker compose stop` to `docker compose down`. `stop`
  is the intended semantic — the containers and their volumes survive, and
  `make down` / `make down-clean` already exist for removal. Only the *coverage* of
  `stop` was wrong.
- Managing the `smoke` profile from the infrastructure helper. Profile-gated services are
  hidden by `config --services` unless the profile is selected, so `llama-cpp-smoke` and
  `llama-cpp-smoke-model-cache` stay out of the derived list; `make smoke-up` owns them.
- Adding shell linting (`shellcheck`/`shfmt`) to `scripts/lint.sh`. That is new tooling,
  not drift.
- Deduplicating the four near-identical Python-service branches in
  `scripts/service-helpers.sh`. They are current and correct; collapsing them is a
  refactor, not a fix.

## Impact

- Affected specs: `infrastructure`.
- Affected files: `scripts/docker-infrastructure.sh`, `services/smoketest/smoke.sh`,
  `Makefile`, `README.md`, `openspec/specs/infrastructure/spec.md`.
- `make smoke-model` goes from always failing to working, restoring the behaviour the
  `infrastructure` spec already required.
- Behaviour change for `make infra-down` and `make infra-restart`: they now also act on
  `dragncards-postgres`, `dragncards-mc-plugin`, `otel-lgtm`, and `lmstudio-proxy`.
  `make infra-up` is unchanged in effect, since those services were already being started
  transitively.
- `make infra-restart` will now also re-run the one-shot `dragncards-mc-plugin` builder,
  which re-copies plugin artifacts into its volume and exits. Idempotent.
- No code, API, or schema changes.
