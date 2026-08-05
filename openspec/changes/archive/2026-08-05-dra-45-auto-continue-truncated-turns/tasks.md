## 1. Establish the mechanism that ends the turn

- [x] 1.1 Confirm no service source reads a stop reason: `finish_reason` and `stop_reason` appear nowhere under any `services/*/src/`, only in `tests/unit/test_bifrost.py` SSE fixtures
- [x] 1.2 Confirm `ChatResponse` (`integrations/bifrost.py`) carries `content`, `tool_calls`, `raw`, `reasoning`, `reasoning_details` and no stop reason
- [x] 1.3 Confirm the non-streaming parser reads only `data["choices"][0]["message"]`, so `finish_reason` — a sibling of `message` in the same choice — is discarded
- [x] 1.4 Confirm the streaming parser reads only `choices[0].delta` through `_extract_delta`, so the terminating chunk that carries `finish_reason` with an empty delta contributes nothing
- [x] 1.5 Confirm production always streams: `PromptRunService.run` always passes `on_delta`, and `chat_completion` sets `stream` from it
- [x] 1.6 Record the exact end-of-turn branch — `prompt_run.py:460` `if not response.tool_calls:` → `complete_job` → `return` — as the line that reports a truncated turn as a successful one
- [x] 1.7 Separate this from the tool-round-limit interrupt at `prompt_run.py:641-663`, which is deliberate, labelled `"interrupted"`, and out of scope

## 2. Capture the stop reason in the client

- [x] 2.1 Add `finish_reason: str | None = None` to `ChatResponse`
- [x] 2.2 Add a module-level helper that reads a stop reason out of one choice in priority order — `finish_reason`, then `native_finish_reason`, then a choice-level or message-level `stop_reason` — and normalises an empty or non-string value to `None`
- [x] 2.3 Populate it in `_parse_chat_response` from `data["choices"][0]`, falling back to a top-level `stop_reason` for a gateway that leaks the Anthropic shape
- [x] 2.4 Populate it in `_stream_chat_completion`, keeping the **last** chunk that carries a non-null value, so a provider that emits it early and a provider that emits it on the final chunk both work
- [x] 2.5 Leave `raw` untouched, so nothing that already reads `raw` changes shape

## 3. One truncation vocabulary

- [x] 3.1 Add `runtime/truncation.py` with a frozen set of stop reasons that mean "cut off at the output cap" and an `is_output_truncated(value)` predicate that lowercases and strips its input
- [x] 3.2 Cover OpenAI `length`, Anthropic `max_tokens`, Gemini/Vertex `MAX_TOKENS` and `max_output_tokens`, OpenAI-shaped `max_completion_tokens`, and the `model_length` / `token_limit` spellings gateways pass through
- [x] 3.3 Return `False` for `None`, the empty string, and any unknown value, so an unrecognised stop reason leaves today's behaviour exactly as it is

## 4. Bounds and the kill switch

- [x] 4.1 Add `auto_continue_truncated_turns: bool = True` to `Settings` with the `AUTO_CONTINUE_TRUNCATED_TURNS` alias
- [x] 4.2 Add `auto_continue_max_continuations: int = 3` with the `AUTO_CONTINUE_MAX_CONTINUATIONS` alias and a validator rejecting a value below 1
- [x] 4.3 Document both in `services/agent-orchestrator/README.md`; no `.env.example` or compose file enumerates the compaction settings either, so there is no second place to update

## 5. Continue the turn inside the existing loop

- [x] 5.1 In `PromptRunService.run`, track a per-turn continuation counter initialised before the round loop
- [x] 5.2 Accumulate each round's output text so a continued turn's `result_text` is the whole answer rather than only the final segment
- [x] 5.3 In the `not response.tool_calls` branch, continue instead of completing when the stop reason is truncating, the feature is enabled, the counter is below the cap, and the context guard allows it
- [x] 5.4 Append the partial assistant content to `messages` only when it is non-empty, then append the continuation instruction as a `user` message
- [x] 5.5 Reset the counter on any round that produced tool calls, so the cap counts consecutive truncations rather than a whole turn's unrelated ones
- [x] 5.6 Complete the turn normally when any condition fails, so every refusal path lands on today's behaviour

## 6. The context-window guard

- [x] 6.1 Resolve the model's context window through `get_model_context_length`, falling back to `settings.context_window_size`, fetched lazily and cached for the life of the turn
- [x] 6.2 Estimate the in-flight request with the existing token estimator rather than a new one, and refuse the continuation when the estimate reaches `context_window_size * context_compaction_threshold`
- [x] 6.3 Confirm the guard is measured *after* the partial content and the instruction would be appended, so the number is the request that would actually be sent
- [x] 6.4 Log the refusal with the estimate, the budget and the stop reason

## 7. Make the seam visible

- [x] 7.1 Persist a `turn_continued` job event and publish it under the durable row's id, carrying `reason`, the raw `finish_reason`, the 1-based `continuation` and `max_continuations`
- [x] 7.2 Confirm no migration is needed: `job_events.event_type` is `VARCHAR(64)` with no enum and no check constraint
- [x] 7.3 Add `turn_continued` to the dashboard's `AggEvent` union in `features/play/lib/play-session-events.ts`
- [x] 7.4 Add it to `STREAM_EVENT_TYPES`, without which the browser subscribes per named type and drops it live until a reconnect
- [x] 7.5 Add it to the pass-through `case` group in `aggregateEvents`, without which the `default:` branch renders it as a tool card that never completes
- [x] 7.6 Add a `case` to the `play-transcript.tsx` renderer, without which it is a blank row with no TypeScript and no lint error
- [x] 7.7 Replace the duplicated (and already four types stale) `ALL_EVENT_TYPES`/`TERMINAL_TYPES` lists in `subagent-output-modal.tsx` with the shared `STREAM_EVENT_TYPES`/`TERMINAL_EVENT_TYPES`, so a subagent's continuation is visible too and the copy cannot drift again
- [x] 7.8 Confirm it is in **neither** terminal set — `job_event_stream.py`'s `TERMINAL_EVENT_TYPES` nor the dashboard's — because a continued turn has not ended
- [x] 7.9 Replay `turn_continued` in `session_transcript.py` as a note on the assistant turn, since the replay loop ignores unknown types and the model would otherwise not know the service resumed it

## 8. Tests

- [x] 8.1 Bifrost unit test: a streamed response whose final chunk carries `finish_reason: "length"` yields `ChatResponse.finish_reason == "length"`
- [x] 8.2 Bifrost unit test: the non-streaming parser reads `finish_reason` from the choice
- [x] 8.3 Bifrost unit test: `native_finish_reason` and an Anthropic-shaped `stop_reason` are read when `finish_reason` is absent, and `finish_reason` wins when both are present
- [x] 8.4 Bifrost unit test: a response with no stop reason anywhere yields `None`
- [x] 8.5 Truncation unit tests: every vocabulary member matches case-insensitively; `stop`, `end_turn`, `tool_calls`, `content_filter`, `""` and `None` do not
- [x] 8.6 Prompt-run test (**the red test**): a truncated response with no tool calls followed by a finishing response produces one job, status `completed`, whose result text contains both segments — this fails on unfixed code
- [x] 8.7 Prompt-run test: the transcript holds a `turn_continued` event between the two `model_output` events, and it is published as well as persisted
- [x] 8.8 Prompt-run test: a response with a non-truncating stop reason completes on the spot and emits no `turn_continued`
- [x] 8.9 Prompt-run test: with the cap set to 1, a model that truncates every time is continued once and then completes, so the loop is bounded
- [x] 8.10 Prompt-run test: with `AUTO_CONTINUE_TRUNCATED_TURNS` off, a truncated response completes exactly as it does today
- [x] 8.11 Prompt-run test: a cancel requested during a continuation chain ends the job as `cancelled` at the next round boundary
- [x] 8.12 Prompt-run test: a request already at the context budget is not continued, and no `turn_continued` is emitted
- [x] 8.13 Config unit test: `AUTO_CONTINUE_MAX_CONTINUATIONS=0` is rejected
- [x] 8.14 Transcript unit test: a replayed `turn_continued` tells the model the service resumed the turn
- [x] 8.15 Dashboard test: `STREAM_EVENT_TYPES` contains `turn_continued`, `aggregateEvents` passes it through, and the transcript renders a visible row for it

## 9. Documentation

- [x] 9.1 Add `turn_continued` to the event-type list in `services/agent-orchestrator/README.md`
- [x] 9.2 Add it to the inline list in `services/agent-orchestrator/AGENTS.md`, and reconcile the two lists, which already disagree about `seat_scope_violation`
- [x] 9.3 Document the two new settings alongside the other worker settings

## 10. Verification

- [x] 10.1 Run `./scripts/lint.sh --fix`
- [x] 10.2 Run `./scripts/test.sh unit` and confirm every suite is at or above its baseline — agent-orchestrator 691, dashboard 682, game-service 476, eval-service 340, history-service 202, shared 38
- [x] 10.3 Run `./scripts/test.sh integration` against the running infrastructure — game-service 66, agent-orchestrator 31, eval-service 17, history-service 8
- [x] 10.4 Run `~/.local/share/pnpm/openspec validate --all` and confirm the only failure is the pre-existing `spec/typed-game-actions` one
- [ ] 10.5 Drive the real worker path end to end through the service's own API with a fake provider returning a truncated response, and confirm the job completes with both segments and a `turn_continued` event — **not performed.** The whole worker path is exercised against a `FakeBifrost` in `tests/unit/test_truncated_turn_continuation.py`, including the cancel, cap, kill-switch and context-budget paths, but nothing drove it through the running service's HTTP API
- [ ] 10.6 Render the resulting transcript in the dashboard and confirm the continuation marker is visible between the two output blocks — **not performed.** Covered only by `features/play/__tests__/play-transcript.test.ts`
