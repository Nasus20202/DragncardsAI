---
name: linear-workflow
description: How work is tracked in Linear on this project - creating issues from reported work, moving status on real events, writing the comment record, and tying issue IDs to git branches and OpenSpec changes. Use when starting, splitting, blocking, finishing, or reporting on any unit of work.
metadata:
  version: "1.0"
---

Linear is where work and its state live; `openspec/` is where a change is specified; a chat log
is not a record. The policy is in [`AGENTS.md`](../../../AGENTS.md) under **Task Management
(Linear)** — this skill is the procedure for carrying it out.

Requires a Linear MCP server. Workspace: team **DragncardsAI**, prefix `DRA`.

## Choosing what to work on

When pulling a set of issues, order them by **priority**, then the owner's **manual order** (the
drag-and-drop position), then **size with the biggest first**. Not quickest-first: small items first
feels productive and strands the expensive work at the end of a session.

`list_issues` only accepts `orderBy` of `createdAt`/`updatedAt` and returns `priority` but not
`sortOrder`, so sort client-side and state which keys were actually available — priority always, size
when estimates are set, manual order only if the owner supplies it.

## Before starting work

1. Find or create the issue. Search first (`list_issues`) — reported work is often already filed.
2. If it does not exist, create it (`save_issue`) **before** touching code:
   - Title: the symptom, in the reporter's terms.
   - Description: the report **verbatim**. Add your reading under a separate `Interpretation:` line
     instead of editing the report — including when it contains an obvious typo, since the raw
     wording is evidence and the reading is opinion.
   - Exactly one label: `Bug`, `Feature`, or `Improvement`.
   - Assignee: the person who owns the outcome, never an agent.
3. Re-read the description to the end. A report often names a second defect after the headline one
   ("...*Also* the rounds are calculated wrongly") — that is a separate issue, so create a sub-issue
   for each independently verifiable part rather than one issue that can never be half-done.
4. Move it to `In Progress` only once the branch and worktree exist.
5. Post the **starting** comment (template below).

## While working

Comment when something *deviates* — not per commit:

- Scope changed, or the fix is not where the issue assumed it was.
- Blocked: say what is blocking, and move the issue back to `Todo` so it does not read as active.
- A finding that belongs to a different issue: file or link that issue, don't bury it here.
- An earlier conclusion in this issue's comments turned out to be wrong: correct it explicitly.

## Finishing

Do not mark `Done` on a delegated agent's report. Verify yourself, then:

1. Squash-merge the worktree branch into the integration branch, one commit following the semantic
   commit convention (e.g. `feat:`, `fix:`, `refactor:`), subject ending ` (DRA-<n>)`.
2. Run the full check set on the merged tip (`./scripts/lint.sh`, `./scripts/test.sh unit`, the
   service test suites, `openspec validate --all`).
3. Drive the running app through the feature or the fixed path where practical (Playwright MCP, not
   tests alone), and name in the comment what was and was not exercised. `Done` means ready for the
   owner's testing, not that a human has already clicked it.
4. Archive the OpenSpec change and sync `openspec/specs/`. Replace every placeholder the archive
   generated — a `TBD` `## Purpose` left behind becomes a false record of what the system does.
5. Post the **finishing** comment, then move the issue to `Done`.
6. Remove the worktree and **delete the merged branch**. Squash-merging means the branch is not an
   ancestor of the integration branch, so `git branch --merged` will not list it — match it to the
   archived change instead of trusting ancestry.

Attach screenshots and recordings to the issue. They must not be left in the repo working tree.

## Naming

| Thing | Form |
| --- | --- |
| Branch | contains `dra-<n>` so Linear links it automatically |
| Worktree directory | `wt-dra<n>` |
| Squash commit subject | semantic commit format (e.g. `feat(scope): ...`), one line, ends with ` (DRA-<n>)`, no AI attribution |
| OpenSpec change directory | `dra-<n>-<slug>` |
| PR body | one `Fixes DRA-<n>` line per issue in the batch — but do NOT open the PR unless the owner asks for it in that moment |

## Delegation

Only the orchestrating agent writes to Linear. Delegated agents report back to it and never comment
on issues: a worktree agent cannot see the merged result or the sibling issues, and parallel writers
interleave half-truths on one issue. Hand a delegated agent the issue text verbatim, not a summary.

## Comment templates

**Starting**

```markdown
**Started** — `<branch>` in `wt-dra<n>`, OpenSpec change `openspec/changes/dra-<n>-<slug>/`.

Reading of the request: <what is being fixed, and what is explicitly out of scope>
Assumptions: <anything ambiguous, and which way it was resolved>
Suspected cause: <file:line evidence, or "unknown — investigating">
```

**Finishing**

```markdown
**Done** — `<sha>` on `<integration branch>`.

Changed:
- `<service>/<file>` — <what and why>

Verified:
- `./scripts/test.sh unit` — <counts before → after>
- End-to-end: <what was driven in the running app, and what was observed>

Spec: `openspec/changes/archive/<date>-<slug>/`
Not done: <deliberate omissions, follow-ups filed as DRA-<n>>
```

**Blocked**

```markdown
**Blocked** — <what is needed, from whom or what>. Moving back to Todo.

Done so far: <what landed, if anything, and where>
```

Evidence, not adjectives: SHAs, paths, counts, commands. "Fixed and tested" records nothing.
Record failures and dead ends too — an issue history containing only successes is not a source of
truth, and the next person repeats the dead end.
