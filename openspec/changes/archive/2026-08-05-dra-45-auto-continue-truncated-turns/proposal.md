# Automatically continue a turn the provider truncated at its output cap

## Why

A long agent turn sometimes stops mid-thought. The job is reported as
**completed**, the transcript shows a partial answer, and the only way forward
is to send a follow-up message saying "continue" (DRA-45).

The cause is that the orchestrator never asks *why* the model stopped.

`ChatResponse` (`integrations/bifrost.py`) carries `content`, `tool_calls`,
`raw`, and reasoning — and no stop reason. Neither parser reads one:

- Non-streaming `_parse_chat_response` reads `data["choices"][0]["message"]`.
  `finish_reason` is a **sibling** of `message` inside the same choice, so it is
  dropped.
- Streaming `_stream_chat_completion` reads only `choices[0].delta`, through
  `_extract_delta`. The terminating chunk carries `finish_reason` with an empty
  delta and therefore contributes nothing. That chunk is retained in
  `raw = {"chunks": [...]}`, but nothing ever reads a stop reason back out of it.

`PromptRunService.run` always passes `on_delta`, so the streaming path is the
only one production uses.

The loop then treats **"no tool calls"** as the sole end-of-turn signal:

```python
if not response.tool_calls:
    logger.info("Job %s completed without further tool calls", job.id)
    await self.complete_job(full_job, response.content, accumulated_job_tokens)
    return
```

A response truncated at the provider's output-token cap has exactly that shape:
some content (often none at all, when a reasoning model spent its whole budget
thinking), no tool calls. It lands in the completion branch and is recorded as a
successful turn. `finish_reason` appears nowhere in any service's `src/` — only
in `tests/unit/test_bifrost.py` fixtures.

So the reporter's hypothesis is right about the mechanism, and the gap is
narrower than "the provider truncates": the service **cannot distinguish**
truncation from a model that finished, and silently reports the first as the
second.

One thing this is *not*: the tool-round-limit interrupt. Exhausting
`worker_max_tool_rounds` (default 64) already ends the job as `"interrupted"`
with an explicit "Please send a follow-up message to continue" message, and the
next run replays a synthetic note about it. That path is deliberate, labelled,
and visible. DRA-45 describes an *unlabelled* stop reported as success, which is
the truncation path.

## What Changes

- **agent-orchestrator (Bifrost client)** — `ChatResponse` gains
  `finish_reason`. Both parsers populate it: the non-streaming parser from
  `choices[0]`, the streaming parser from the last chunk that carries a non-null
  one. Provider vocabularies are read in priority order — `finish_reason`, then
  OpenRouter's `native_finish_reason`, then an Anthropic-shaped `stop_reason` —
  so a passthrough value is not lost.
- **agent-orchestrator (new `runtime/truncation.py`)** — one place that decides
  whether a stop reason means "cut off at the output cap". Matches
  case-insensitively across vendor vocabularies: OpenAI `length`, Anthropic
  `max_tokens`, Gemini/Vertex `MAX_TOKENS`, and the `max_output_tokens` /
  `max_completion_tokens` / `model_length` / `token_limit` variants gateways
  pass through. Everything else — `stop`, `end_turn`, `tool_calls`,
  `content_filter`, an unknown value, or no value at all — is **not**
  truncation, so a model that chose to stop is never forced onward.
- **agent-orchestrator (prompt run)** — when a response has no tool calls *and*
  a truncating stop reason, the turn is continued automatically instead of
  completed: the partial assistant content and a continuation instruction are
  appended to the in-flight messages and the loop takes another round. A
  `turn_continued` job event is persisted and published first, so the transcript
  shows the seam.
- **agent-orchestrator (bounds)** — two new settings.
  `AUTO_CONTINUE_TRUNCATED_TURNS` (default `true`) is the kill switch;
  `AUTO_CONTINUE_MAX_CONTINUATIONS` (default `3`) is the per-turn cap. Beyond
  the cap the turn completes exactly as it does today. Continuations also
  consume rounds of the existing `worker_max_tool_rounds` loop, so they can
  never outlive the round budget.
- **agent-orchestrator (context guard)** — before each continuation the
  in-flight request is estimated against the model's context window. A
  continuation that would push the request to or past
  `context_compaction_threshold` of the window is refused and the turn completes,
  so the service never drives a truncate → continue → truncate spiral into an
  over-window request.
- **dashboard** — the transcript renders `turn_continued` as its own entry
  between the partial output and its continuation, naming the stop reason and
  the continuation number, so an automatic resume is never mistaken for one
  unbroken model answer.

## Non-goals

- **Raising or setting `max_tokens`.** The output cap is the session's model
  configuration and stays the operator's choice. This change makes a turn
  survive the cap; it does not change it.
- **Retrying a truncated *tool call*.** When the cap lands mid-way through a
  tool call's arguments, `_finalize_streamed_tool_calls` already falls back to
  `{"raw": "<partial json>"}` and the tool answers with an error the model can
  recover from. Those rounds have tool calls, so the loop continues on its own;
  the stop reason is recorded for observability and nothing else changes.
- **Changing the tool-round-limit interrupt.** It stays `"interrupted"` with its
  own message and its own replay note.
- **Mid-turn compaction.** Compaction rewrites persisted history and runs once
  at job start; it cannot shrink a request already in flight. The context guard
  refuses the continuation instead.
- **A new job status.** A turn that was continued and then finished is
  `"completed"`, because it did finish. The `turn_continued` events are what
  record that the service helped.

## Impact

- Affected specs: `agent-orchestrator` (stop-reason capture, automatic
  continuation and its bounds), `dashboard` (rendering the new event).
- Affected code:
  `services/agent-orchestrator/src/agent_orchestrator/integrations/bifrost.py`,
  `services/agent-orchestrator/src/agent_orchestrator/runtime/truncation.py` (new),
  `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py`,
  `services/agent-orchestrator/src/agent_orchestrator/config.py`,
  `services/dashboard` transcript event rendering.
- **No database migration.** `job_events.event_type` is `VARCHAR(64)` with no
  enum and no check constraint, so `turn_continued` needs no schema change.
- New environment variables: `AUTO_CONTINUE_TRUNCATED_TURNS`,
  `AUTO_CONTINUE_MAX_CONTINUATIONS`. Both have defaults; no deployment change is
  required.
