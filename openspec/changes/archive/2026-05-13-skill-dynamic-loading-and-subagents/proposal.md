## Why

Skills today are loaded once at job start — the entire `SKILL.md` is injected into the system prompt and stays there for the full conversation. This means large skills waste context tokens even when only a fraction of the content is relevant, there is no visibility into when or what a skill loaded, and a running agent cannot delegate subtasks to a fresh agent with its own model, skills, and tool scope. Adding dynamic skill content loading and a subagent spawning capability addresses all three gaps and makes the system more capable, observable, and efficient.

## What Changes

- **Skill summary in system prompt** — Only a short description (name + one-sentence summary) is placed in the initial system prompt. Full skill content is no longer injected at startup.
- **Dynamic skill loading tools** — Built-in (non-MCP) tools `load_skill` and `load_skill_reference` are exposed to the agent. `load_skill` returns the named skill's `SKILL.md` plus a list of available reference files, and `load_skill_reference` loads one chosen markdown reference file on demand.
- **Skill linked references** — Skills may include additional markdown reference files anywhere under the skill directory. They are listed when the skill is loaded and fetched individually only when the agent asks for a specific relative file path.
- **`skill_loaded` event** — When the agent calls `load_skill`, a `skill_loaded` event is emitted and stored like any other job event, so the UI can display it in the transcript.
- **Subagent spawning tool** — A built-in tool `spawn_subagent` is exposed **only on master (top-level prompt) jobs**. It creates a new session (optionally inheriting model config and skill/MCP assignments), submits a prompt, streams the child job to completion, and returns the result text. Each delegation step emits `subagent_started` and `subagent_completed` events visible in the transcript.
- **Dashboard event rendering** — The transcript shows minimal single-line entries for subagent lifecycle events. Skill loads and MCP tool calls remain collapsible rows.
- **Subagent panel in config sidebar** — A new panel above the context usage widget shows live subagents at a glance (collapsed by default) and all subagents when expanded. Each row has an [open] button.
- **Subagent output modal with live SSE** — Clicking [open] opens a modal with the child job's full transcript. If the child is still running the modal connects to the child job's SSE stream and renders events live.

## Capabilities

### New Capabilities

- `llm-capabilities`: Full catalogue of what the agent can do — MCP tool invocation, the skill system (`load_skill`, `load_skill_reference`, linked references, `skill_loaded` event), subagent delegation (`spawn_subagent`, `subagent_started/completed/failed` events, dashboard drill-down), and dashboard rendering of all agent activity. This spec covers the **what**, not the how.

### Modified Capabilities

- `agent-orchestrator`: Technical implementation of the above — system prompt construction (summary-only skills), built-in tool dispatch infrastructure in the worker, `parent_job_id` DB column, and child session/job lifecycle management. **Convention: `agent-orchestrator` spec holds implementation details (worker mechanics, DB schema, internal APIs). `llm-capabilities` spec holds the high-level view (what the LLM sees, what events are emitted, what the dashboard renders). Keep them separated at archive.**
- `dashboard`: Context health indicator now also refreshes after a configuration save, not only after job completion or compaction.

## Impact

- `services/agent-orchestrator/src/agent_orchestrator/runtime/worker.py` — built-in tool dispatch loop; `load_skill`, `load_skill_reference`, and `spawn_subagent` handlers; child job wait via LiveEventBus subscription; new event types.
- `services/agent-orchestrator/src/agent_orchestrator/schemas/jobs.py` — new event type values (documentation only; `event_type` is an open string).
- `services/agent-orchestrator/src/agent_orchestrator/storage/models.py` — `parent_job_id` nullable FK column on `Job`.
- `services/dashboard/features/play/components/play-transcript.tsx` — minimal single-line renderers for subagent events; collapsible rows for `skill_loaded`.
- `services/dashboard/features/play/components/play-event-card.tsx` — label + render fallbacks for new event types.
- `services/dashboard/features/play/components/play-config-panel.tsx` — new subagent panel above context usage widget; collapsed/expanded states.
- `services/dashboard/features/play/components/play-workspace.tsx` — call `refreshContextMetadata` at the end of a successful `handleSaveConfiguration`.
- New dashboard component: subagent output modal with live SSE connection to child job event stream.
- **Database schema change**: `parent_job_id` nullable FK added to `jobs` table via Alembic migration.
- No breaking API changes.
