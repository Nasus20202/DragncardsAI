## ADDED Requirements

### Requirement: Service agent guides are discoverable as `CLAUDE.md`

A directory carrying an `AGENTS.md` guide SHALL also expose that guide under the
`CLAUDE.md` name, as a relative symlink rather than a duplicated copy, so that
directory-scoped agent tooling discovers the guide closest to the files being changed while
`AGENTS.md` remains the single source of truth.

#### Scenario: Service directory exposes its guide under both names

- **WHEN** a service directory under `services/` contains an `AGENTS.md`
- **THEN** the same directory SHALL contain a `CLAUDE.md` symlink whose target is
  `AGENTS.md`
- **AND** the symlink SHALL be tracked by git as a symlink (mode `120000`) with a relative
  target, so it resolves in clones, git worktrees, and container copies

#### Scenario: Guide content is never duplicated

- **WHEN** a service's `AGENTS.md` is edited
- **THEN** reading `CLAUDE.md` in that directory SHALL yield the edited content with no
  second file to update
