## Why

The agent-orchestrator's LLM runtime had several compounding reliability problems: a vague system prompt that failed to guide tool selection, a tool round limit that caused hard failures with no context carry-over, and no way for a subagent to know it shouldn't try to spawn further subagents. Together these caused frequent job failures, wasted context, and poor multi-turn continuity.

## What Changes

- **System prompt** — Replaced three generic lines with a detailed, structured prompt covering identity, tool discipline, context management, game-service MCP guidance, subagent use cases, error handling, and response style.
- **Subagent tool descriptions** — `spawn_subagent` description now names the exact large-payload tools that must always be delegated and states it is only available to top-level jobs.
- **Tool round limit** — Raised default from 32 to 64. On limit hit, job is now marked `"interrupted"` (new terminal status) instead of `"failed"`; a graceful completion event is published so SSE clients and `wait_for_subagent` close cleanly.
- **Interrupted/failed job context replay** — `list_completed_jobs_for_replay` now includes `interrupted` and `failed` jobs so their partial tool calls and model output feed into the next job's context. Synthetic assistant notes are injected to tell the model how to interpret the prior run.
- **Reasoning on by default** — New `DEFAULT_REASONING_ENABLED` / `DEFAULT_REASONING_EFFORT` env vars and `DashboardConfig` fields enable reasoning for all new dashboard sessions by default. Smoketest explicitly opts out.

## Capabilities

### Modified Capabilities

- `agent-orchestrator`: Job lifecycle now includes `"interrupted"` terminal status; replay query now includes failed and interrupted jobs; system prompt and tool descriptions updated for reliability and delegation discipline; reasoning defaults configurable via env vars.

## Impact

- `services/agent-orchestrator/src/agent_orchestrator/runtime/system_prompts.py` — system prompt rewritten
- `services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py` — `spawn_subagent` / `wait_for_subagent` descriptions updated
- `services/agent-orchestrator/src/agent_orchestrator/config.py` — `worker_max_tool_rounds` 32 → 64
- `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py` — tool round limit path changed to graceful interrupt
- `services/agent-orchestrator/src/agent_orchestrator/repositories/jobs.py` — `mark_job_interrupted` added
- `services/agent-orchestrator/src/agent_orchestrator/repositories/context.py` — replay query includes interrupted + failed
- `services/agent-orchestrator/src/agent_orchestrator/runtime/session_transcript.py` — synthetic context notes for non-completed jobs
- `services/agent-orchestrator/src/agent_orchestrator/runtime/job_event_stream.py` — `"interrupted"` added to `TERMINAL_JOB_STATUSES`
- `services/dashboard/features/shared/lib/types.ts` — `DashboardConfig` extended
- `services/dashboard/features/config/lib/dashboard-config.ts` — reads reasoning env vars
- `services/dashboard/features/play/lib/session-draft.ts` — reasoning default driven by config
- `services/smoketest/smoke.sh` — `DEFAULT_REASONING_ENABLED=false`
- `docker-compose.yaml` — reasoning env vars added
