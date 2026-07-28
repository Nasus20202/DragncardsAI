# DragncardsAI Agent Guide

Read this file before making changes in this repository.

## Scope

These instructions apply to the whole repository unless a deeper `AGENTS.md` overrides them.

This file is the single source of truth for agent instructions, and is read by every
assistant setup used on this project (Claude Code, OpenCode, and any other). Tool-specific
entry files such as `CLAUDE.md` are thin pointers to this file and must stay that way — an
instruction written only in a tool-specific file silently does not apply to everyone else.
Write rules in terms of *what* to do, naming a specific tool or command only as an example.

## Project Overview

- This repository contains an LLM-powered Marvel Champions bot for DragnCards.
- Top-level areas include `services/`, `scripts/`, `external/`, `openspec/`, and `.github/`.
- Primary local workflows are documented in `README.md`.

## Useful Reading

- Start with [`README.md`](README.md) for local setup, test commands, and service URLs.
- Read [`services/game-service/README.md`](services/game-service/README.md) when working on DragnCards session control, MCP tools, or game actions.
- Read [`services/agent-orchestrator/README.md`](services/agent-orchestrator/README.md) when working on agent sessions, skills, providers, or background jobs.
- Read files nearest to the change before introducing new patterns.

## Service-Level Guides

Service-specific AGENTS.md files override these instructions:

- [`services/dashboard/AGENTS.md`](services/dashboard/AGENTS.md) - Frontend development with Hero UI components
- [`services/game-service/AGENTS.md`](services/game-service/AGENTS.md) - Game service patterns, DragnLang actions, Phoenix Channels
- [`services/agent-orchestrator/AGENTS.md`](services/agent-orchestrator/AGENTS.md) - Session lifecycle, jobs, provider configuration

## Working Rules

- Prefer the smallest correct change that fits the existing code style.
- Check nearby code before introducing new abstractions, helpers, or patterns.
- Do not revert or overwrite user changes that are unrelated to your task.
- Keep secrets out of commits and examples.

## Working Preferences

- Do substantive work in an isolated git worktree rather than directly on the checked-out branch.
- Remove a worktree as soon as its work is merged or abandoned, in the same session that finishes it — do not leave worktrees behind for a later cleanup. Each dashboard worktree costs roughly 250k inodes once its `node_modules` is installed, and a scratch filesystem that runs out of inodes stops *every* write, including the writes needed to clean it up. Delete `node_modules` when a worktree's checks are done, remove the worktree when its branch merges, and `git worktree prune` after. Removing a worktree does not delete its branch, so it is always the reversible half of the cleanup.
- **Delete a feature branch once its work is merged into the integration branch.** A merged branch is leftover clutter, not a safety net — the work lives in the integration branch's history. Do this as part of the same cleanup that removes the worktree, so branches do not accumulate across sessions. Two cautions: squash-merging means a merged branch is *not* an ancestor of the integration branch, so `git branch --merged` will not list it and ancestry is the wrong test — match the branch to the OpenSpec change that archived its work instead. And record the branch tips (`git branch --format='%(refname:short) %(objectname)'`) somewhere outside the repo before a bulk delete, so a mistake stays recoverable. Never delete `main`, the current integration branch, a branch that is checked out in some worktree, or a `features/*` branch the owner created; and never delete a remote branch that backs an open pull request.
- Delegate as much as reasonably possible to delegated agents; fan out independent pieces in parallel.
- Run implementation agents on the most capable model available, never a fast or cheap tier (in Claude Code, pass `model: opus`).
- Multi-feature sessions branch off a single integration branch: each feature/agent gets its own worktree branch off the integration branch, works independently, then merges back as **one squash commit per feature**.
- **Never open a pull request unless the owner explicitly asks for it in that moment.** Merging features into the integration branch and pushing it is the end of the agent's job; the PR is the owner's call, every time. A rule stating that PRs are opened from the integration branch describes *which branch* a PR comes from — it is not standing permission to open one, and neither is an unanswered earlier question about it. Silence is not consent.
- **One** integration branch per session, chosen once and kept. Work that arrives later in the session joins the existing integration branch — a new source of work (issues instead of chat reports, a new batch of bugs) is not a new session and does not justify a second integration branch. Two live integration branches mean two PRs that stack on each other for no reason.
- Skip the worktree/delegation overhead for trivial one-off edits.
- **Durability comes from committing often on the local branch, not from pushing.** A session can end at any moment — on a usage limit, a crash, a closed terminal — and uncommitted work is the only work that dies. Commit each coherent piece as it lands (a passing test, a migration, a section of a proposal), with `wip:` on the subject while the state is partial; squash-on-merge means intermediate commits cost nothing. Do not push to `origin` merely to feel safe: the local commit is what preserves the work, and pushing is a separate, deliberate act. Keep a resume file (`.agents/BATCH-STATE.md`) current in the same commits, so the next session recovers the plan and the decisions from the branch itself rather than from a chat log that no longer exists.
- Commits use a single-line message and must NOT include any AI attribution (no `Co-Authored-By` trailer naming an assistant).
- Every change goes through the OpenSpec workflow (a change in `openspec/changes/`), even small fixes.
- After implementing a change, ensure the main specs in `openspec/specs/` are brought up to date (sync/archive) so specs reflect reality when the work is done.
- **`TBD` is never acceptable in an OpenSpec artifact.** Neither is any other placeholder standing in for content that was meant to be written: `TODO`, `???`, `to be decided`, an empty section under a heading, or a `## Purpose` left holding the generator's own "update after archive" note. Archiving a change is what creates or updates a spec, so archiving is exactly when every placeholder it produced must be replaced with real prose — a spec is the durable record of what the system does, and a placeholder there is a lie that outlives the change that introduced it. Filling them in is the responsibility of whoever archives, not a follow-up for someone else. Before archiving, grep the change and the specs it touches for placeholder text and resolve each one; if something genuinely cannot be decided yet, write what is actually known and what the open question is, in prose, rather than leaving a marker.
- After each bigger implementation, run the code-review, security-review, and simplification passes (the `/code-review`, `/security-review`, and `/simplify` commands where the setup provides them) and address their findings before considering the work done.
- Use `pnpm` / `pnpx` for all Node tooling — never `npm`, `npx`, or `yarn`.
- Always verify new features end-to-end by driving the running app through the Playwright MCP server and clicking through the feature — don't rely on unit/integration tests alone.
- Track work in Linear, per **Task Management (Linear)** below.

## Task Management (Linear)

Linear holds *what* work exists and what state it is in. `openspec/` holds *how* a change is
specified. A chat log holds nothing durable — anything recorded only there is lost.

Workspace: team **DragncardsAI**, issue prefix `DRA`. Statuses `Backlog → Todo → In Progress →
Done`, plus `Canceled` and `Duplicate`. Labels `Bug`, `Feature`, `Improvement`.

The step-by-step procedure and the comment templates live in the `linear-workflow` skill
([`.agents/skills/linear-workflow/SKILL.md`](.agents/skills/linear-workflow/SKILL.md)); the rules
below are the policy it implements. Reaching Linear needs a Linear MCP server configured in the
assistant setup.

Assistant-facing skills like that one live under `.agents/skills/` and are symlinked into
`.claude/skills/` and `.opencode/skills/`. They must NOT go in the repo-root `skills/` directory:
that is a *runtime* skill root, enumerated by the agent-orchestrator and eval-service and copied
into their images, so anything placed there is offered to the game-playing agent and the judge as
a Marvel Champions skill. `skills/` is for game and domain knowledge only.

### Work order when pulling issues from Linear

Sort the fetched issues by, in this order:

1. **Priority** — Urgent, then High, Medium, Low, then No priority.
2. **Manual order** — the position the owner set by dragging in the Linear UI.
3. **Size, biggest first** — the estimate, largest first, so the heavy work starts earliest rather than being left until capacity is gone.

Do not substitute "quickest first". Starting with the small items feels productive and leaves the
expensive work stranded at the end of a session.

Known gap to be honest about: the Linear MCP's `list_issues` exposes `orderBy` for `createdAt` and
`updatedAt` only, and its results carry `priority` but not the manual `sortOrder`. So priority is
sortable directly, size is sortable when estimates are set, and manual order has to be read from the
Linear UI or supplied by the owner. Say which keys were actually available rather than implying a
full sort happened.

### One issue per unit of work

- If it warrants an OpenSpec change, it warrants a Linear issue; the two are one-to-one. Edits to
  agent instruction files, editor config, and other pure process changes need neither.
- Work reported in chat gets an issue **before** work starts, not after.
- Record the request in the reporter's own words. Quote verbatim where the wording is ambiguous or
  contains an obvious typo, and note the interpretation as a separate remark rather than silently
  correcting it — the raw report is evidence, the reading is opinion.
- One issue = one independently verifiable defect or capability. An issue that turns out to contain
  two gets split into sub-issues, so its status can mean something.
- Every issue carries exactly one of `Bug` / `Feature` / `Improvement` and is assigned to the person
  who owns the outcome. Agents do not own issues.
- Nothing is dropped silently: use `Canceled` or `Duplicate`, with a comment saying why.

### Status changes follow real events, not intentions

- **Todo → In Progress** when the branch and worktree exist and work has begun — not when the work
  is discussed or planned.
- **In Progress → Done** only once the change is merged into the integration branch, the full check
  set passes on the merged tip, and the OpenSpec change is archived. A delegated agent reporting
  success is not Done; Done requires the orchestrating agent's own verification.
- Blocked work moves back to `Todo` with a comment naming the blocker. It does not sit in
  `In Progress` where it reads as active.

### Names tie Linear, git, and OpenSpec together

- Branch names contain `dra-<n>` so Linear links them automatically. Linear's suggested branch name
  is fine, shortened if unwieldy.
- Worktree directory: `wt-dra<n>`.
- Squash commit subject ends with ` (DRA-<n>)` — still a single line, still no AI attribution.
- OpenSpec change directory: `dra-<n>-<slug>`.
- The PR body lists one `Fixes DRA-<n>` line per issue in the batch.

### Comments are the record

Post to the issue at three moments, and not per commit:

1. **Starting** — branch, worktree, OpenSpec change path, and how the request was read, including
   assumptions and anything found ambiguous.
2. **Finishing** — the squash commit SHA, what changed per service and file, test counts before and
   after, how it was verified end-to-end (what was actually driven in the running app), the archived
   spec path, and explicitly what was left out of scope.
3. **Deviating** — scope changes, blockers, findings that belong to a different issue (link it), and
   earlier conclusions that turned out to be wrong.

- Record failures and dead ends too. An issue history containing only successes is not a source of
  truth, and the next person repeats the dead end.
- Evidence, not adjectives: SHAs, paths, counts, commands. "Fixed and tested" records nothing.
- Attach screenshots and recordings to the issue; they do not belong in the repo working tree.

### Delegation

- Only the orchestrating agent writes to Linear. Delegated agents report back to it and never
  comment on issues themselves: a worktree agent cannot see the merged result or the sibling issues,
  and parallel writers interleave half-truths on the same issue.
- Hand a delegated agent the issue text verbatim, not a summary of it.

### Batches

- A batch of issues shares one integration branch; each issue gets its own worktree branch off it
  and is squash-merged back as a single commit. The PR is opened from the integration branch.
- Issues reach `Done` on merge into the integration branch. The PR landing on `main` is tracked on
  the PR itself, not as a second status hop.

### When Linear is unreachable

Do the work, say plainly in the final report that it was not recorded, and write the missing
comments once Linear is reachable again. Never let the chat log become the record by default.

## Keep the Surrounding Files Current

A change is not finished when the code works. Every change must also update whatever else it made
stale — in the same change, not as a follow-up:

- **`README.md`** (root and the service's own) — setup steps, service URLs and ports, test commands,
  and any list that enumerates the services.
- **OpenTelemetry configuration** — a service that emits no telemetry is invisible in production.
  Adding or renaming a service means wiring its tracing, metrics, and logs the same way the existing
  services do, reusing the shared setup helper rather than hand-rolling per-service bootstrap.
- **Docker and infrastructure configuration** — `docker-compose.yaml`, the service `Dockerfile`,
  `.env.example` files, and anything that derives the infra service list.
- **Scripts and make targets** — `scripts/*.sh` and any equivalent make targets, especially the ones
  that enumerate services to lint, test, build, or start. A script with a hardcoded service list is a
  place a new service gets silently omitted.
- **Swagger / API index** and any other page that lists endpoints or services.

The recurring failure this prevents: a service is added, its code works, and it is quietly missing
from the telemetry stack, the API index, and half the scripts — each omission found weeks later as a
separate bug. When a change touches the set of services, or a port, or a required environment
variable, grep for the *existing* services by name to find every list that will need the new one too,
and say in the final report which ancillary files you updated.

## Repo Conventions

- Use `scripts/test.sh unit` for unit tests.
- Use `scripts/test.sh integration` for integration tests when the Docker stack is running.
- Use `scripts/docker.sh build` when a rebuild is needed.
- Follow existing structure inside each service instead of forcing one pattern across the monorepo.

## Data Storage

- Services must NOT store any state in memory.
- Use PostgreSQL for persistent data.
- Use Valkey for ephemeral/stateful data that doesn't require persistence.

## Agent Guidance

- Start by reading `README.md` and the files closest to the requested change.
- When working in `openspec/`, preserve the existing OpenSpec workflow and artifact format.
- When working in `external/`, treat vendored or upstream code carefully and avoid unnecessary edits.
- Explain assumptions briefly when behavior is ambiguous.
- Before finishing a task, you are expected to run:
  - `./scripts/lint.sh --fix`
  - `./scripts/test.sh unit`
  - `./scripts/docker-infrastructure.sh start` followed by `./scripts/test.sh integration`
