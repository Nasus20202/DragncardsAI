## Context

The agent-orchestrator's worker currently injects every assigned skill's full `SKILL.md` into the system prompt at job start. For skills with large reference material this burns context tokens regardless of whether the agent uses that skill during the run. There is no event emitted when a skill is used, so the dashboard has no visibility into skill activity. The worker also has no way to delegate to a fresh agent — all reasoning happens in a single multi-turn loop.

The worker's tool dispatch already handles an open-ended MCP tool catalog. Adding a small set of built-in tools that are handled by the worker itself (before the MCP lookup) is a minimal change to the existing loop.

## Goals / Non-Goals

**Goals:**
- Reduce default context consumption by keeping only skill summaries in the system prompt
- Give the agent on-demand access to full skill content and linked reference files
- Make skill loading visible in the transcript via a dedicated event type
- Allow a master job to delegate subtasks to isolated child agents with their own session
- Make subagent activity visible in the parent job's transcript

**Non-Goals:**
- Recursive subagent hierarchies (children cannot spawn children)
- Persistent or reusable subagent sessions after job completion
- Changes to how skills are discovered, registered, or assigned via the API
- Changes to the MCP protocol or external MCP servers

## Decisions

### Decision: Built-in tools handled before MCP lookup

The worker tool dispatch loop checks the tool name against a built-in registry first. If matched, a local handler runs instead of calling an MCP server. Unknown tools fall through to the existing MCP mapping.

**Why**: No new infrastructure. Built-in tools appear in the OpenAI tool list alongside MCP tools, so the LLM can call them identically. The dispatch order (built-in → MCP → error) is explicit and easy to test.

**Alternative considered**: Expose a dedicated "orchestrator MCP server" that the worker auto-attaches. Rejected — adds a network hop and a new service process for logic that lives entirely in the worker.

### Decision: Skill summaries extracted from first non-blank non-heading SKILL.md line

The summary for the system prompt is extracted by `SkillRegistry.get_summary(skill_name)` which reads `SKILL.md` and returns the first line that is not blank and does not start with `#`. This is a cheap heuristic that works for the existing skill format without requiring any frontmatter convention.

**Why**: All current skills open with a heading (`# Skill: X`) followed by a description sentence. No metadata format changes needed.

**Alternative considered**: YAML frontmatter `summary:` field. More explicit but requires retrofitting all existing skills.

### Decision: Linked references loaded from markdown files anywhere under the skill directory

`SkillRegistry.load_skill_content(skill_name)` returns `SKILL.md` plus an inventory of every `*.md` file found anywhere under the skill directory except `SKILL.md` itself, sorted by relative path. The actual reference contents are fetched later via `load_skill_reference(skill_name, reference_name)`, where `reference_name` is that relative path. No other file types are included.

**Why**: This matches the actual skill package layout already present in the repo and avoids forcing all skills into a single subdirectory convention. The agent can still choose the specific files it needs without loading everything into context.

### Decision: spawn_subagent restricted to master jobs via parent_job_id column

A nullable `parent_job_id` column is added to the `jobs` table. Jobs created by `spawn_subagent` have this set to the spawning job's id. The worker checks `job.parent_job_id is None` when building the tool list — if not None, `spawn_subagent` is omitted.

**Why**: The restriction must survive a worker restart, so it needs to be in the DB, not in-memory state. The parent reference also enables future query patterns (e.g. "show all child jobs for this master job").

**Alternative considered**: A separate `is_master` boolean. Rejected — a FK to the parent is strictly more informative.

### Decision: spawn_subagent inherits model config from parent session by default

If no model config override is provided, the child session copies the parent session's `provider_id`, `model_name`, `gateway_options`, and `provider_options`. Skills and MCP assignments are inherited only if explicitly listed by name in the `spawn_subagent` call.

**Why**: The agent knows which model it's on and can pass overrides if needed. Defaulting to the same model avoids requiring the agent to know provider routing details. Explicit skill/MCP inheritance prevents accidentally giving the child more tools than intended.

### Decision: Child job wait uses LiveEventBus subscription, not DB polling

The `spawn_subagent` handler SHALL subscribe to the child job's channel on the `LiveEventBus`
(Valkey pub/sub) rather than polling `repository.get_job` in a loop. The handler awaits a
`completion`, `failure`, or `cancellation` event on that channel to detect terminal state.

**Why**: The worker already uses Valkey pub/sub for SSE streaming — using the same mechanism for
child job completion avoids 150+ DB reads per subagent on a 30-second run, gives instant
notification, and provides a natural hook for forwarding child progress events to the parent.

**Alternative considered**: Poll `repository.get_job` at `worker_poll_interval_seconds`. Simpler
to implement but works against the existing architecture and scales poorly when a master job spawns
multiple subagents.

### Decision: Subagent UI is a panel in the config sidebar, not inline in the transcript

Subagent status and output are surfaced through a dedicated panel inside the config sidebar,
positioned above the context usage widget. The transcript shows only a minimal single-line entry
per subagent event. Clicking [open] on a panel row opens a modal.

**Why**: The transcript is already the primary reading surface — inlining child transcripts or
expanding subagent rows there competes with the parent conversation. The sidebar panel gives the
user a persistent at-a-glance view of running subagents without scrolling, and the modal gives
full detail on demand without losing the parent context or navigating away.

**Alternatives considered**:
- Inline expanding block in transcript (reasoning block style) — noisy when multiple subagents run;
  forces the user to scroll to find running ones.
- Right-side drawer — both sidebars are already in use; a third drawer z-fights and crowds the layout.
- Full centre-column takeover — loses parent context while reading child.
- Top drawer above transcript — anchoring and scroll interaction awkward with existing streaming indicator.

### Decision: Subagent panel collapsed state shows only live subagents

By default the panel is collapsed and shows only currently running subagents. The user expands it
to see completed and failed subagents. The panel is hidden entirely when no subagents exist for the
current job.

**Why**: Live subagents are the urgent signal — the user may be waiting for them. Completed ones
are history. Defaulting to live-only keeps the panel compact and meaningful at a glance.

### Decision: Subagent modal uses live SSE for running jobs, static events for terminal jobs

When the modal opens for a running child job it connects a new `EventSource` to
`/jobs/{child_job_id}/events/stream`. When the child job is already in a terminal state it fetches
stored events via `GET /jobs/{child_job_id}/events` and renders statically. The SSE connection is
closed when the modal unmounts or the job reaches a terminal state.

**Why**: Live SSE reuses the exact same infrastructure already used by the parent transcript.
No new backend work required — the child job's event stream is already accessible. The modal is
effectively a second SSE consumer pointed at a different job ID.

## Risks / Trade-offs

- **Context round-trip cost** — The agent now needs a tool call to load a skill, adding one LLM round before skill content is available. This is acceptable because skill loading happens at most once per skill per job, and the token saving on large skills outweighs the round-trip cost.
  
- **parent_job_id migration** — A nullable column addition. Safe on PostgreSQL with no table rewrites, but requires a schema migration file.

- **Subagent depth limit** — Children cannot call `spawn_subagent`. This is enforced in the tool list only; there is no DB-level enforcement. A future schema could add a `depth` counter if recursive spawning becomes desirable.

- **Child session billing** — Each subagent creates a full session. If the master spawns many subagents in a loop the session table could grow quickly. Mitigated by terminating child sessions immediately and by the existing `worker_max_tool_rounds` cap.

## Migration Plan

1. Add `parent_job_id` nullable FK column to `jobs` table via a new Alembic migration.
2. Deploy updated worker — new built-in tools are inert until the LLM calls them.
3. No API contract changes; existing clients continue to work.
4. Rollback: revert migration (column is nullable, no existing rows are affected).

## Open Questions

- None outstanding.
