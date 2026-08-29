# DRA-86: Include Running Job Events in Session Context Metadata Estimate

## Why
The dashboard polls `GET /sessions/{session_id}/context` every 5 seconds during active generation (`useContextMetadataPolling`). However, the context usage breakdown remains unchanged during multi-tool or long prompt runs because `build_context_metadata` and `list_completed_jobs_for_replay` only inspect jobs in `completed`, `interrupted`, or `failed` statuses. The user prompt and recorded in-flight `JobEvent`s (tool calls, tool results, model output) of an active `running` job are omitted from the transcript estimate until the job completes.

## What Changes
- Update session transcript context estimation in `agent-orchestrator` to include `running` jobs when calculating session context health metadata (`GET /sessions/{session_id}/context`).
- Reconstruct the in-flight prompt and recorded `JobEvent` history for running jobs so that live polling reflects growing context as tool calls and model responses occur.
- Add unit tests verifying that active running jobs with intermediate tool calls and user prompts are included in context metadata estimates.

## Capabilities
### Modified Capabilities
- `agent-orchestrator`: Context metadata endpoint estimates context usage including active running jobs and their recorded events.
