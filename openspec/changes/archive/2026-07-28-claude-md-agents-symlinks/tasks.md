## 1. Add the symlinks

- [x] 1.1 Create `CLAUDE.md -> AGENTS.md` relative symlinks in
      `services/agent-orchestrator`, `services/dashboard`, `services/eval-service`,
      `services/game-service`, and `services/history-service`.
- [x] 1.2 Confirm git records each one as a symlink (mode `120000`) and that no
      `.gitignore` rule excludes `CLAUDE.md`.

## 2. Specs and verification

- [x] 2.1 Add an agent-instruction discoverability requirement to
      `openspec/specs/infrastructure/spec.md`.
- [x] 2.2 `./scripts/lint.sh --fix` and `./scripts/test.sh unit` pass.
