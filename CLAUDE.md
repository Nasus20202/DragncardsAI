# DragncardsAI

This project uses `AGENTS.md` as the single source of truth for agent instructions.
Service-specific guides live in each service's `AGENTS.md` and override the root.

@AGENTS.md

## Working Preferences

- Do substantive work in an isolated git worktree rather than directly on the checked-out branch.
- Delegate as much as reasonably possible to subagents; fan out independent pieces in parallel.
- Multi-feature sessions branch off a single integration branch: each feature/agent gets its own worktree branch off the integration branch, works independently, then merges back as **one squash commit per feature**. The PR is opened from the integration branch.
- Skip the worktree/delegation overhead for trivial one-off edits.
- Commits use a single-line message and must NOT include a `Co-Authored-By: Claude` trailer (or any Claude attribution).
- Every change goes through the OpenSpec workflow (a change in `openspec/changes/`), even small fixes.
- After implementing a change, ensure the main specs in `openspec/specs/` are brought up to date (sync/archive) so specs reflect reality when the work is done.
- After each bigger implementation, run `/code-review`, `/security-review`, and `/simplify` and address their findings before considering the work done.
- Use `pnpm` / `pnpx` for all Node tooling — never `npm`, `npx`, or `yarn`.
- Always verify new features end-to-end with the Playwright MCP — drive the running app and click through the feature, don't rely on unit/integration tests alone.

