## 1. System Prompt

- [x] 1.1 Rewrite `BASE_SYSTEM_PROMPT_PARTS` in `system_prompts.py` with identity, tool discipline, context discipline, game-service MCP guidance, subagent section, error handling, and response style sections
- [x] 1.2 Add context discipline section explicitly forbidding direct calls to large-payload tools (`get_game_state`, `search_cards_marvel_champions`, etc.) and explaining the verbatim-context-injection problem
- [x] 1.3 Add subagent section with `spawn_subagent` / `wait_for_subagent` mechanics, use-case list, subagent nesting guidance, and self-contained prompt guidelines
- [x] 1.4 Update `test_build_system_prompt_includes_existing_skills_and_skips_missing` to match new opening line

## 2. Subagent Tool Descriptions

- [x] 2.1 Update `spawn_subagent` description in `builtin_tools.py` to name forbidden direct-call tools, state top-level-only availability, and explain permanent context injection risk
- [x] 2.2 Add "subagents cannot spawn further subagents" guidance to system prompt and `spawn_subagent` description

## 3. Tool Round Limit and Interrupted Status

- [x] 3.1 Raise `worker_max_tool_rounds` default from 32 to 64 in `config.py`
- [x] 3.2 Add `mark_job_interrupted` method to `repositories/jobs.py` (sets `status="interrupted"`, `error_code="tool_round_limit"`, `result_text`)
- [x] 3.3 Add `"interrupted"` to `TERMINAL_JOB_STATUSES` in `job_event_stream.py`
- [x] 3.4 Replace `raise RuntimeError("tool round limit exceeded")` in `prompt_run.py` with graceful interrupt: publish `"completion"` event, call `mark_job_interrupted`, return normally
- [x] 3.5 Update `test_worker_fails_when_tool_round_limit_is_exceeded` assertions to expect `status="interrupted"` and `error_code="tool_round_limit"`

## 4. Failed and Interrupted Job Context Replay

- [x] 4.1 Update `list_completed_jobs_for_replay` in `repositories/context.py` to include `"interrupted"` and `"failed"` jobs (keep `"cancelled"` excluded)
- [x] 4.2 Add synthetic `role: assistant` notes in `_reconstruct_job_replay_items` in `session_transcript.py` for `"interrupted"` and `"failed"` job statuses
- [x] 4.3 Update `test_get_context_metadata_uses_replay_window_not_full_history` token budget assertion to accommodate longer system prompt

## 5. Reasoning Default

- [x] 5.1 Add `defaultReasoningEnabled: boolean` and `defaultReasoningEffort: "low" | "medium" | "high"` to `DashboardConfig` interface in `types.ts`
- [x] 5.2 Add `parseReasoningEffort` helper and read `DEFAULT_REASONING_ENABLED` / `DEFAULT_REASONING_EFFORT` env vars in `dashboard-config.ts` (defaults: `true`, `"medium"`)
- [x] 5.3 Add `DEFAULT_REASONING_ENABLED` and `DEFAULT_REASONING_EFFORT` env var passthrough to dashboard service in `docker-compose.yaml` (defaults: `true`, `"medium"`)
- [x] 5.4 Update `buildDefaultReasoningDraft(config)` and `extractReasoningDraft(options, config)` in `session-draft.ts` to accept and use `DashboardConfig`
- [x] 5.5 Set `DEFAULT_REASONING_ENABLED=false` in `services/smoketest/smoke.sh`
## 6. Split System Prompt (Top-Level vs Subagent)

- [x] 6.1 Add `SUBAGENT_SYSTEM_PROMPT_PARTS` and `build_subagent_system_prompt` to `system_prompts.py` with subagent identity, direct large-payload tool permission, nesting blocked notice, and concise-answer response style
- [x] 6.2 Import `build_subagent_system_prompt` in `prompt_run.py` and use it when `job.parent_job_id is not None`, otherwise use `build_system_prompt`
- [x] 6.3 Add unit tests for `build_subagent_system_prompt`: verify it does NOT contain `spawn_subagent` delegation section and DOES contain large-payload tool direct-call permission
