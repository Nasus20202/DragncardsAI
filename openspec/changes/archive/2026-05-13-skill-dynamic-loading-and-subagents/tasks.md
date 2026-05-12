## 1. Database Migration

- [x] 1.1 Create Alembic migration to add nullable `parent_job_id` FK column to `jobs` table referencing `jobs.id`
- [x] 1.2 Add `parent_job_id` mapped column to `Job` ORM model in `storage/models.py`
- [x] 1.3 Verify migration applies cleanly on a fresh DB and existing rows are unaffected

## 2. Skill Registry Enhancements

- [x] 2.1 Add `get_summary(skill_name) -> str` method to `SkillRegistry` that returns the first non-blank, non-heading line of SKILL.md
- [x] 2.2 Add `load_skill_content(skill_name) -> str` method that returns full SKILL.md plus an inventory of every `*.md` file under the skill directory except `SKILL.md`
- [x] 2.3 Add `list_reference_files(skill_name)` and `load_reference_content(skill_name, reference_name)` helpers for explicit per-reference loading by relative path
- [x] 2.4 Write unit tests for `get_summary`, `load_skill_content`, and reference helpers covering: summary extraction, no-summary fallback, reference inventory, and explicit reference loads

## 3. System Prompt Refactor

- [x] 3.1 Update `build_system_prompt` in `system_prompts.py` to call `skill_registry.get_summary()` per assigned skill instead of `load_markdown()`
- [x] 3.2 Add an "Available skills" section to the system prompt listing each skill name and summary, with instructions to call `load_skill(<name>)` before using the skill and `load_skill_reference(<skill_name>, <reference_name>)` for specific references
- [x] 3.3 Update unit tests for `build_system_prompt` to assert summaries (not full content) appear and both skill-loading instructions are present

## 4. Built-in Tool Infrastructure

- [x] 4.1 Create `runtime/builtin_tools.py` with a `BuiltinToolRegistry` class that holds a dict of tool name → handler callable and produces OpenAI tool definitions
- [x] 4.2 Update `WorkerService.__init__` to accept and store a `BuiltinToolRegistry`
- [x] 4.3 Update the worker tool dispatch loop to check built-in tools first; emit `tool_call` and `tool_result` events for built-in calls using `assignment="builtin"` and `server_url=None`
- [x] 4.4 Update `app.py` / dependency wiring to construct and inject `BuiltinToolRegistry` into `WorkerService`

## 5. load_skill Built-in Tool

- [x] 5.1 Implement `load_skill` handler in `builtin_tools.py`: validate skill is assigned to session, call `skill_registry.load_skill_content()`, return `SKILL.md` plus a reference inventory as tool result
- [x] 5.2 Emit `skill_loaded` event (with `skill_name` and `reference_file_count`) via `repository.append_event` and `live_event_bus.publish` on successful load
- [x] 5.3 Return an error tool result (without emitting `skill_loaded`) when skill is not assigned
- [x] 5.4 Wire `load_skill` into `BuiltinToolRegistry` at startup
- [x] 5.5 Add `load_skill_reference` built-in tool for explicit per-reference loading and wire it into `BuiltinToolRegistry`
- [x] 5.6 Write unit tests for the skill-loading handlers: success path, unassigned skill error, reference file count in event payload, explicit reference load, missing reference error

## 6. spawn_subagent Built-in Tool

- [x] 6.1 Implement `spawn_subagent` handler: create child session, copy model config from parent (unless override provided), assign requested skills and MCPs, submit prompt job with `parent_job_id` set
- [x] 6.2 Wait for child job completion by subscribing to the child job's `LiveEventBus` channel (Valkey pub/sub); cancel child job and unsubscribe if parent cancellation is requested mid-wait
- [x] 6.3 Emit `subagent_started` event on parent job when child session and job are created (payload: `child_session_id`, `child_job_id`, `prompt_preview`)
- [x] 6.4 Emit `subagent_completed` or `subagent_failed` event on parent job when child reaches terminal state
- [x] 6.5 Terminate child session after child job reaches terminal state
- [x] 6.6 Restrict `spawn_subagent` to master jobs: add `is_master_job(job) -> bool` check (`parent_job_id is None` and `job_type == "prompt"`) and include the tool in the list only when True
- [x] 6.7 Wire `spawn_subagent` into `BuiltinToolRegistry`
- [x] 6.8 Write unit tests for `spawn_subagent`: success path, child failure, parent cancellation propagation, tool absent on compaction job, tool absent on child job

## 7. Dashboard — Transcript Event Renderers

- [x] 7.1 Add `skill_loaded` label and collapsible renderer to `play-event-card.tsx` (label: "Skill loaded", shows skill name and reference file count)
- [x] 7.2 Add `skill_loaded` handling in `play-transcript.tsx` aggregator and `AggEventRow` renderer
- [x] 7.3 Add minimal single-line renderers for `subagent_started`, `subagent_completed`, `subagent_failed` in `play-transcript.tsx` (status indicator + prompt/result preview text, no expansion)
- [x] 7.4 Add all new event types to the `EventSource` listener list in `play-workspace.tsx`

## 8. Dashboard — Subagent Panel

- [x] 8.1 Add subagent panel component to `play-config-panel.tsx` positioned above the context usage widget
- [x] 8.2 Panel collapsed state: show only running subagents (sourced from parent job events filtered by `subagent_started` without a matching `subagent_completed`/`subagent_failed`); hide panel entirely when none exist
- [x] 8.3 Panel expanded state: show all subagents for current job — running (pulsing indicator), completed (✓ + result preview), failed (✗ + error code); toggle via [∨ all] / [∧ less] button
- [x] 8.4 Each subagent row shows prompt preview and an [open] button that opens the subagent output modal

## 9. Dashboard — Subagent Output Modal

- [x] 9.1 Create `subagent-output-modal` component; accepts `child_job_id` and `is_running: bool` as props
- [x] 9.2 On mount: if `is_running`, connect `EventSource` to `/api/proxy/orchestrator/jobs/{child_job_id}/events/stream`; if terminal, fetch stored events via `GET /jobs/{child_job_id}/events`
- [x] 9.3 Render child job events using existing event rendering components (reuse `play-transcript.tsx` or `play-event-card.tsx` renderers)
- [x] 9.4 On unmount: close any open `EventSource` connection
- [x] 9.5 When child job reaches a terminal event (`completion`, `failure`, `cancellation`) while modal is streaming: stop SSE, display final state
- [x] 9.6 Wire [open] button in subagent panel to open the modal with the correct `child_job_id` and running state

## 10. Dashboard — Context Refresh on Save

- [x] 10.1 In `play-workspace.tsx`, call `refreshContextMetadata(selectedSession.id)` at the end of a successful `handleSaveConfiguration`, after `loadAllJobs`

## 11. Integration & Verification

- [x] 11.1 Run existing unit tests (`scripts/test.sh unit agent-orchestrator`) and fix any regressions
 - [x] 11.2 Add integration test: session with skill assigned, agent calls `load_skill`, verify `skill_loaded` event appears in job events
- [x] 11.3 Add integration test: master job calls `spawn_subagent`, verify child session created and terminated, `subagent_started` and `subagent_completed` events on parent job
- [x] 11.4 Rebuild Docker image (`scripts/docker.sh build`) and verify service starts cleanly

## 12. Post-Archive — Spec Extraction

After this change is archived, the `agent-orchestrator` main spec will contain all the requirements merged from the delta. The high-level overview (LLM-visible behaviour) currently mixed into `agent-orchestrator` must be moved to `llm-capabilities` to preserve the boundary established in this change.

- [ ] 12.1 Review `openspec/specs/agent-orchestrator/spec.md` after archive and identify any requirements that describe LLM-visible behaviour (tool contracts, event payloads, dashboard rendering) rather than internal implementation
- [ ] 12.2 Move those requirements verbatim into `openspec/specs/llm-capabilities/spec.md` under the appropriate sections
- [ ] 12.3 Replace moved requirements in `openspec/specs/agent-orchestrator/spec.md` with a cross-reference comment pointing to `llm-capabilities/spec.md`
- [ ] 12.4 Verify the scope comments at the top of both spec files accurately reflect their remaining content after the move

## 13. spawn_subagent — Non-Blocking Parallel Dispatch

- [x] 13.1 Refactor `make_spawn_subagent_handler` in `builtin_tools.py` to return a tool result immediately after enqueueing the child job (do not `await subscriber.get()`); return `{ child_job_id, name }` where `name` is the first 50 chars of the prompt
- [x] 13.2 Name the child session from the prompt: call `repository.update_session(child_session.id, name=prompt[:50])` before returning the tool result
- [x] 13.3 Add `name` field to the `subagent_started` event payload
- [x] 13.4 Launch a detached `asyncio.create_task(_monitor_child(...))` coroutine that subscribes to the child job's `LiveEventBus`, waits for a terminal event, then appends `subagent_completed` / `subagent_failed` on the parent job and terminates the child session
- [x] 13.5 Update tool description: "Spawn a child agent with a given prompt. Returns immediately with child_job_id and name; the child runs in parallel. You may spawn multiple subagents and continue working."
- [x] 13.6 Update unit tests: success path now checks that the handler returns immediately with `child_job_id` in result; add test that two spawns can be issued in sequence before either completes
- [x] 13.7 Update integration test `test_spawn_subagent_creates_child_and_emits_events` to match new non-blocking contract

## 14. Dashboard — Session Title from First Prompt

- [x] 14.1 In `play-workspace.tsx` `handleSubmitPrompt`, after a successful `submitPrompt` call, check if this is the first job in the session; if so call `updateSession(sessionId, { name: prompt.slice(0, 60) })` and refresh the session list
- [x] 14.2 Track "first prompt submitted" per session: use `sessionJobs.length === 0` before submission as the signal (jobs list not yet containing the new job)

## 15. Dashboard — Inline Subagent Cards in Chat

- [x] 15.1 Create `SubagentCard` component in `services/dashboard/features/play/components/subagent-card.tsx`; accepts `childJobId: string`, `name: string`, `isRunning: boolean`; renders a collapsible card with the child job's transcript using `aggregateEvents` + `AggEventRow`
- [x] 15.2 `SubagentCard` when `isRunning=true`: open `EventSource` to `/api/proxy/orchestrator/jobs/{childJobId}/events/stream?after=0`, append raw events to local state, run through `aggregateEvents`, render via `AggEventRow`
- [x] 15.3 `SubagentCard` when `isRunning=false` (or on terminal SSE event): fetch stored events via `getJobEvents(childJobId)`, display statically; close any open `EventSource`
- [x] 15.4 Render `SubagentCard` list in `play-workspace.tsx` inside the centre chat column, between the main `PlayTranscript` and `PlayPromptBox`; source entries from `subagentEntries` state (already computed)
- [x] 15.5 Remove `SubagentPanel` from `play-config-panel.tsx` (props `subagentEntries` and `onOpenSubagent`); remove `SubagentOutputModal` from `play-workspace.tsx`
- [x] 15.6 Remove `subagentOutputModal` state and `onOpenSubagent` callback from `play-workspace.tsx`
