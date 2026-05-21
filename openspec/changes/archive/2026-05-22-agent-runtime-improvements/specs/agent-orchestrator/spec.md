## ADDED Requirements

### Requirement: Interrupted job terminal status
When the tool round limit is reached and the job has not produced a final text-only response, the worker SHALL mark the job with status `"interrupted"` (not `"failed"`). The worker SHALL:
1. Publish a `"completion"` event with a message explaining the interruption and asking the user to send a follow-up.
2. Call `mark_job_interrupted` on the repository, which sets `status = "interrupted"`, `error_code = "tool_round_limit"`, and `result_text` to the interruption message.
3. Return normally (not raise an exception).

The `"interrupted"` status SHALL be included in `TERMINAL_JOB_STATUSES`.

#### Scenario: Tool round limit hit produces interrupted job
- **WHEN** a job exhausts `worker_max_tool_rounds` iterations without returning a text-only response
- **THEN** the job status SHALL be `"interrupted"` with `error_code = "tool_round_limit"`
- **AND** a `"completion"` SSE event SHALL be published with the interruption message

#### Scenario: Interrupted job is not retried
- **WHEN** a job is marked `"interrupted"`
- **THEN** it SHALL NOT be re-queued regardless of `max_attempts`

### Requirement: Interrupted and failed jobs included in context replay
When `multi_turn_memory` is enabled, the worker SHALL include `"interrupted"` and `"failed"` jobs (in addition to `"completed"` jobs) when replaying prior job events. `"cancelled"` jobs SHALL remain excluded.

After reconstructing the event replay items for a non-completed job, the worker SHALL append a synthetic `role: assistant` message:
- For `"interrupted"` jobs: `"[Previous turn was interrupted by the tool round limit. The partial work above is preserved. Continue from where this left off.]"`
- For `"failed"` jobs: `"[Previous turn failed before completing. Partial tool calls above may be incomplete. Resume the task taking the partial work into account.]"`

#### Scenario: Interrupted job partial work replayed
- **WHEN** a new job starts and the prior job has status `"interrupted"`
- **THEN** the prior job's tool calls and tool results SHALL be replayed into the messages list
- **AND** a synthetic assistant note SHALL follow indicating the interruption

#### Scenario: Failed job partial work replayed
- **WHEN** a new job starts and the prior job has status `"failed"`
- **THEN** the prior job's tool calls and tool results SHALL be replayed into the messages list
- **AND** a synthetic assistant note SHALL follow indicating the failure

#### Scenario: Cancelled job still excluded from replay
- **WHEN** a new job starts and a prior job has status `"cancelled"`
- **THEN** that prior job's events SHALL NOT appear in the messages list

### Requirement: Subagent jobs use a dedicated system prompt
Top-level jobs (where `parent_job_id` is null) SHALL receive the full system prompt built by `build_system_prompt`, which includes the subagent delegation section, context discipline rules, and large-payload tool blacklist.

Subagent jobs (where `parent_job_id` is not null) SHALL receive a separate, leaner prompt built by `build_subagent_system_prompt`, which:
- Identifies the job as a subagent with a bounded task
- Instructs it to call large-payload tools directly (`get_game_state`, `search_cards_marvel_champions`, etc.)
- Explicitly states that `spawn_subagent` and `wait_for_subagent` are unavailable and nesting is blocked
- Instructs it to return a concise, structured answer only

The subagent prompt SHALL NOT contain the top-level context-discipline rules that forbid large-payload tool calls, nor the `spawn_subagent`/`wait_for_subagent` usage guidance.

#### Scenario: Top-level job receives full prompt
- **WHEN** a job with `parent_job_id = null` is started
- **THEN** the system prompt SHALL contain the subagent delegation section and the large-payload tool blacklist

#### Scenario: Subagent job receives lean prompt
- **WHEN** a job with `parent_job_id != null` is started
- **THEN** the system prompt SHALL NOT contain `spawn_subagent` delegation instructions
- **AND** SHALL instruct the agent to call large-payload tools directly
- **AND** SHALL state that `spawn_subagent` is unavailable


The system prompt SHALL identify the agent as an AI assistant for Marvel Champions on DragnCards and state its core responsibilities: set up games, manage the board, recommend plays, explain rules, and take game actions via tools.

#### Scenario: System prompt contains domain identity
- **WHEN** a job is started for any session
- **THEN** the system prompt SHALL contain "DragnCardsAI" and reference "Marvel Champions"

### Requirement: System prompt enforces tool usage discipline
The system prompt SHALL instruct the model to avoid speculative tool calls, prefer targeted tools, batch independent calls in a single round, and never repeat the same call twice in one job.

#### Scenario: No redundant tool calls in system prompt guidance
- **WHEN** the system prompt is rendered
- **THEN** it SHALL contain instructions against duplicate or speculative tool calls

### Requirement: System prompt enforces context discipline
The system prompt SHALL instruct the model that every tool result is appended verbatim to context and replayed in every future turn. It SHALL explicitly forbid calling the following tools directly in the main job: `get_game_state`, `search_cards_marvel_champions`, `export_game_state_snapshot`, `load_game_state_snapshot`, `reset_game`, and any tool returning a card list or full board JSON.

#### Scenario: Large-payload tools blacklisted in system prompt
- **WHEN** the system prompt is rendered
- **THEN** it SHALL name `get_game_state` and `search_cards_marvel_champions` as tools that must never be called directly in the main job

### Requirement: System prompt defines subagent use cases
The system prompt SHALL describe `spawn_subagent` and `wait_for_subagent`, list use cases that require subagent delegation (card catalog research, board state analysis, multi-card setup, play recommendation, rules look-up), and provide guidance on writing self-contained subagent prompts.

#### Scenario: Subagent section present in system prompt
- **WHEN** the system prompt is rendered
- **THEN** it SHALL contain a "Subagents" section describing `spawn_subagent` and `wait_for_subagent`

### Requirement: System prompt explains subagent nesting is blocked
The system prompt SHALL state that if `spawn_subagent` is not in the tool list, the job is already running as a subagent, and subagents SHALL call large-payload tools directly and return a concise answer rather than attempting further delegation.

#### Scenario: Subagent self-detection guidance present
- **WHEN** the system prompt is rendered
- **THEN** it SHALL contain the instruction to check whether `spawn_subagent` is available before attempting delegation

### Requirement: System prompt provides tool round limit recovery guidance
The system prompt SHALL instruct the model that if the tool round limit is exhausted mid-task, it SHALL summarise what was completed and what remains, and ask the user to send a follow-up message to continue.

#### Scenario: Tool round limit recovery guidance present
- **WHEN** the system prompt is rendered
- **THEN** it SHALL reference the tool round limit and a recovery action (follow-up message)

### Requirement: spawn_subagent tool description enforces delegation at tool-selection time
The `spawn_subagent` tool description SHALL state that it is only available to top-level jobs, name the tools that must always be delegated (at minimum `search_cards_marvel_champions`, `get_game_state`, `export_game_state_snapshot`, `load_game_state_snapshot`, `reset_game`), and explain that direct calls to those tools inject tokens permanently.

#### Scenario: spawn_subagent description names forbidden direct-call tools
- **WHEN** the tool catalog is presented to the model
- **THEN** the `spawn_subagent` description SHALL name `search_cards_marvel_champions` and `get_game_state` as tools that must be delegated

#### Scenario: spawn_subagent description states top-level-only availability
- **WHEN** the tool catalog is presented to the model
- **THEN** the `spawn_subagent` description SHALL state it is only available to top-level jobs

### Requirement: Reasoning enabled by default for dashboard sessions
New dashboard sessions SHALL have reasoning enabled by default. The default effort level SHALL be configurable via the `DEFAULT_REASONING_EFFORT` env var (default: `medium`). The default enabled state SHALL be configurable via `DEFAULT_REASONING_ENABLED` (default: `true`).

#### Scenario: New session draft has reasoning enabled
- **WHEN** a user opens the dashboard and creates a new session
- **THEN** the session draft SHALL have `reasoning.enabled = true` and `reasoning.effort` equal to the configured default

#### Scenario: Smoketest sessions have reasoning disabled
- **WHEN** the smoketest environment starts the dashboard stack
- **THEN** `DEFAULT_REASONING_ENABLED` SHALL be set to `false` so new smoketest sessions do not request reasoning

## MODIFIED Requirements

### Requirement: Prior job event replay
When `multi_turn_memory` is enabled, the job worker SHALL replay prior job events for the session into the messages list before the current user prompt.

Eligible jobs for replay are those with status `"completed"`, `"interrupted"`, or `"failed"` (excluding `"cancelled"` and the current job itself).

Replay order SHALL be: for each prior job in chronological order — user prompt, assistant output, tool calls and results interleaved, optional synthetic status note (for non-completed jobs), then continue to next job.

If a `CompactionRecord` exists for the session, the worker SHALL:
1. Inject the compaction summary as a system message
2. Replay only jobs created **after** the `CompactionRecord.covers_up_to_job_id`

If replay limits are configured on the session, the worker SHALL apply them after reconstructing the eligible message history:
1. `context_recent_message_limit` bounds the number of replayed prior conversational messages by recency
2. `context_recent_tool_exchange_limit` bounds the number of replayed prior tool exchanges by recency
3. A tool exchange SHALL include both the assistant tool call and its matching tool result
4. Compaction summary messages SHALL NOT count against either limit

#### Scenario: No prior jobs, no compaction record
- **WHEN** a job starts for a session with no prior jobs and `multi_turn_memory: true`
- **THEN** the messages list SHALL contain only the system prompt and current user prompt

#### Scenario: Prior jobs exist, no compaction record
- **WHEN** a job starts for a session with N prior completed jobs and no `CompactionRecord`
- **THEN** the messages list SHALL begin with the system prompt, followed by all prior job events replayed in order, then the current user prompt

#### Scenario: Prior interrupted job replayed with synthetic note
- **WHEN** a job starts and the immediately prior job has status `"interrupted"`
- **THEN** the interrupted job's events SHALL be replayed, followed by the synthetic interruption note, before the current user prompt

#### Scenario: Compaction record exists
- **WHEN** a job starts and a `CompactionRecord` exists for the session
- **THEN** the messages list SHALL begin with the original system prompt, then the compaction summary as a second system message, then only events from jobs after `covers_up_to_job_id`, then the current user prompt

#### Scenario: Replay history limited by message count
- **WHEN** a session has `context_recent_message_limit` configured and eligible conversational history exceeds that count
- **THEN** the worker SHALL include only the most recent replayable conversational messages up to the configured limit before appending the current user prompt

#### Scenario: Replay history limited by tool exchanges
- **WHEN** a session has `context_recent_tool_exchange_limit` configured and eligible replay history contains more tool exchanges than allowed
- **THEN** the worker SHALL include only the most recent replayable tool exchanges up to the configured limit
- **AND** SHALL retain each included exchange as an assistant tool call plus its matching tool result

#### Scenario: State-heavy exchanges displaced by newer state-heavy exchanges
- **WHEN** replay history contains multiple state-heavy game-service tool exchanges and the configured tool-exchange budget cannot include all of them
- **THEN** the worker SHALL favor the newest state-heavy exchange over older state-heavy exchanges
- **AND** SHALL use remaining tool-exchange budget for other recent exchanges when available
