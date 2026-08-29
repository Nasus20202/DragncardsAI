# Tasks: Include Running Job Events in Session Context Metadata Estimate

- [x] 1. Update session transcript replay queries in `agent-orchestrator`
  - [x] 1.1 Update `list_completed_jobs_for_replay` in `services/agent-orchestrator/src/agent_orchestrator/repositories/context.py` to accept statuses or include `running` jobs when querying for context estimation.
  - [x] 1.2 Verify `build_context_metadata` and `build_message_history` in `services/agent-orchestrator/src/agent_orchestrator/runtime/session_transcript.py` properly reconstruct prompt and event items for running jobs.
- [x] 2. Add unit and integration tests for running job context estimation
  - [x] 2.1 Add test in `services/agent-orchestrator/tests/unit/test_session_transcript.py` asserting that a running job with prompt and tool events is included in context metadata.
  - [x] 2.2 Add API test in `services/agent-orchestrator/tests/unit/test_api_context.py` or equivalent verifying `GET /sessions/{id}/context` reports higher `tokens_used` when a job is running with events.
- [x] 3. Validation and QA
  - [x] 3.1 Run `./scripts/lint.sh --fix`.
  - [x] 3.2 Run `./scripts/test.sh unit`.
  - [x] 3.3 Run `openspec validate --all`.
