# Service `AGENTS.md` guides must be discoverable as `CLAUDE.md`

## Why

Every service keeps its own agent guide at `services/<service>/AGENTS.md`, and the root
`AGENTS.md` declares that those service guides override the repository-level rules. Only
the repository root pairs that convention with a `CLAUDE.md` (a real file that `@`-imports
`AGENTS.md`).

Claude Code discovers directory-scoped instructions by looking for `CLAUDE.md` as it walks
toward the files being edited. Because no service directory has one, an agent working
inside `services/dashboard/` or `services/game-service/` never automatically picks up that
service's guide — it only sees the root instructions. The service guides are the ones that
carry the load-bearing, override-the-root rules (Hero UI usage in the dashboard, DragnLang
and Phoenix Channel patterns in game-service, session-lifecycle rules in the
orchestrator), so the guide most specific to the change is precisely the one that goes
unread unless a human remembers to point at it.

## What Changes

- Each service directory that already has an `AGENTS.md` gains a sibling `CLAUDE.md`
  **symlink** pointing at it: `services/agent-orchestrator`, `services/dashboard`,
  `services/eval-service`, `services/game-service`, `services/history-service`.
- A symlink (git mode `120000`) rather than a copy or a stub file, so `AGENTS.md` stays
  the single source of truth with no second body of text to drift out of sync.
- The repository root is left as it is: it already has a `CLAUDE.md`, and that file adds
  working-preference content of its own on top of importing `AGENTS.md`.

## Non-goals

- Changing the content of any `AGENTS.md`.
- Replacing the root `CLAUDE.md` with a symlink — it is not a pure mirror of the root
  `AGENTS.md`.
- Adding guides to directories that do not have an `AGENTS.md` today (`services/bifrost`,
  `services/otel`, `services/smoketest`, `skills/`, `scripts/`).

## Impact

- Affected specs: `infrastructure` (agent-instruction discoverability).
- Affected files: five new symlinks under `services/*/CLAUDE.md`.
- No code, API, schema, or build changes. Symlink targets are relative and resolve inside
  the same directory, so they survive clones, worktrees, and container copies of the repo.
