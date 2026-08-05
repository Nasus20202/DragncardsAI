# Design: automatic continuation of truncated turns

Auto-continue is a loop that spends the owner's money against a paid provider
without being asked. Every decision below is about keeping that loop bounded,
observable, and impossible to enter by accident.

## Context

`PromptRunService.run` is a `for _ in range(worker_max_tool_rounds)` loop. Each
round calls the gateway, streams reasoning and output into durable job events,
and then branches on one thing:

```python
if not response.tool_calls:
    await self.complete_job(full_job, response.content, accumulated_job_tokens)
    return
```

"No tool calls" is doing two jobs at once: it means "the model answered" *and*
"the model stopped for any other reason". Truncation at the provider's
output-token cap produces the second while looking exactly like the first.

The stop reason is available and thrown away. In the non-streaming parser
`finish_reason` sits beside `message` in the choice and only `message` is read;
in the streaming parser only `choices[0].delta` is read, and the chunk that
carries `finish_reason` has an empty delta. Production always streams
(`on_delta` is always passed), so the streaming path is the one that matters.

## Decision 1: capture the stop reason in the client, not the loop

`ChatResponse` gains `finish_reason: str | None`, populated by both parsers.

The streaming parser already accumulates every chunk into `raw["chunks"]`, so
the value could have been dug out of `raw` at the call site. Rejected: `raw` has
two different shapes (`{"chunks": [...]}` when streaming, the whole response body
when not), and `extract_tokens_from_response` already shows what happens when a
caller has to know which — it silently handles only one of them. Normalising
once, where the two shapes are produced, keeps every consumer shape-blind.

Read order within a choice: `finish_reason`, then `native_finish_reason`, then a
top-level or message-level `stop_reason`.

- `finish_reason` is the OpenAI-compatible field, and Bifrost's
  `/openai/chat/completions` endpoint — the one this client posts to — speaks
  that shape.
- `native_finish_reason` is OpenRouter's passthrough of the upstream provider's
  own value, and OpenRouter is a configured provider. It is consulted second so
  a normalised `length` always wins over a vendor spelling of the same thing.
- `stop_reason` is the Anthropic spelling. A gateway that proxies an Anthropic
  response without full normalisation leaks it, and reading it costs nothing.

For streaming, the **last chunk carrying a non-null value wins**. Providers send
it on the final chunk, but some emit per-choice reasons earlier; taking the last
one is correct in both cases.

## Decision 2: one truncation vocabulary, matched conservatively

`runtime/truncation.py` owns the whole question, as a frozen set plus a
predicate that lowercases and strips its input.

Treated as truncation: `length` (OpenAI), `max_tokens` (Anthropic),
`max_output_tokens` and `max_completion_tokens` (Vertex / newer OpenAI-shaped
APIs), `MAX_TOKENS` (Gemini, matched case-insensitively), `model_length` and
`token_limit` (values gateways have been observed to pass through).

Everything else is *not* truncation, including the empty string, `None`, and any
value the set does not know. This asymmetry is deliberate and is the safety
property that matters most: an unrecognised stop reason means the turn completes
exactly as it does today. The failure mode of a too-small set is the status quo —
the user types "continue". The failure mode of a too-broad set is spending money
forcing a model to keep talking after it decided it was done.

**Alternative rejected:** infer truncation from the shape of the output — empty
content, no tool calls, or content that does not end in sentence punctuation.
This is a guess, it fires on legitimate short answers, and it would force a model
onward for reasons unrelated to any provider limit. The whole point of the change
is to stop treating one signal as evidence of a different thing.

## Decision 3: continue in-loop, keep the job status honest

The continuation is a `continue` in the existing round loop, not a new job and
not a new status.

```python
if not response.tool_calls:
    if <truncated and allowed>:
        await self._record_turn_continued(...)
        if response.content:
            messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": CONTINUATION_INSTRUCTION})
        continuations += 1
        continue
    await self.complete_job(...)
    return
```

Three consequences follow from staying inside the loop, and each of them is a
requirement in its own right:

- **Cancellation keeps working, for free.** The first statement of every
  iteration is the existing `get_job_cancellation_requested` check, so a cancel
  during a continuation chain is honoured at the next round boundary — the same
  latency a user already gets when cancelling during a tool call. No new
  cancellation path means no new way to get it wrong.
- **Continuations are bounded twice.** Each one consumes a round of
  `worker_max_tool_rounds`, so even a misconfigured continuation cap cannot make
  a turn outlive the round budget. If the round budget runs out first, the
  existing `"interrupted"` path takes over unchanged.
- **A continued turn that finishes is `"completed"`.** It did finish. Inventing a
  status would break every consumer of `TERMINAL_JOB_STATUSES` and the replay
  rules keyed on it, to record something the `turn_continued` events already say
  more precisely.

The assistant message is appended **only when the partial content is non-empty**.
A reasoning model can spend its entire output budget thinking and return no text
at all, and some providers reject an assistant message with empty content. The
continuation instruction is a `user` message so it occupies the position the
manual "continue" occupied, which is the behaviour being automated.

**Alternative rejected:** enqueue a real follow-up job with the prompt
"continue". It reproduces the manual workaround faithfully, but it costs a full
context replay per continuation, it splits one logical turn across job rows that
the dashboard and the evaluation pipeline both treat as separate turns, and it
loses the in-flight `messages` list — which is precisely the context the
continuation needs.

## Decision 4: bounds and the kill switch

Two settings, because the brief asks for a cap *and* a way to turn the behaviour
off, and collapsing them into "cap = 0 means off" makes the disabled state
indistinguishable from a misconfiguration.

- `AUTO_CONTINUE_TRUNCATED_TURNS` (bool, default `true`) — off restores the
  current behaviour exactly: a truncated turn completes, and the only new
  artefact is the debug log line.
- `AUTO_CONTINUE_MAX_CONTINUATIONS` (int, default `3`, validated `>= 1`) — the
  per-turn cap. Three is chosen against the shape of the problem: the reported
  symptom is a turn that needed *one* manual nudge, so three covers the observed
  case with headroom while capping the worst case at three extra paid calls per
  turn rather than the round budget's sixty-four.

The counter is per turn, and it resets on any round that produced tool calls.
A turn that truncates, continues, calls a tool, works for twenty rounds and
truncates again gets a fresh budget, because that second truncation is a new
occurrence and not evidence of a stuck loop. What the cap exists to stop is
consecutive truncations — a model that will not stop being truncated — and those
are counted exactly.

When the cap is reached the turn completes normally, and the `turn_continued`
events already in the transcript are what tell the user the service tried. The
manual "continue" still works from there, which is the pre-change behaviour and
therefore a safe floor.

## Decision 5: the context-window guard

Each continuation makes the request strictly longer, and DRA-33 established that
the request estimate can already exceed the context window before any
continuation happens. Continuing into that is the truncate → continue → truncate
spiral the brief warns about.

Compaction cannot help here. `maybe_auto_compact` runs once, at job start, and it
works by rewriting *persisted history* — it has no effect on the `messages` list
already assembled in memory for this turn. There is no correct way to compact
mid-turn without discarding the very partial output the continuation depends on.

So the guard refuses instead of shrinking. Before each continuation the request
that *would be sent* — the in-flight `messages` plus the partial assistant
content and the continuation instruction, plus the tool definitions — is
estimated with the existing `estimate_tokens_for_messages` and
`estimate_tokens_for_tools`, and compared against
`context_window_size * context_compaction_threshold`. That is the same budget
line auto-compaction uses, so "too big to continue" and "too big to send" mean
the same thing in one place. Over the line, the turn completes normally and the
refusal is logged with the estimate and the budget; under it, the continuation
proceeds.

The candidate list is measured *after* the messages a continuation would add,
not before, because a guard that measures the request it is not about to send is
a guard that lets the request it is about to send through.

**Rebase note.** DRA-33 landed `runtime/context_estimate.py` after this change's
base commit. `estimate_request` there is the sum of exactly these two primitives
over the same four request components, so this guard is measuring the same thing
by the same means and not a second estimator. When this branch is rebased onto
that tip, the guard should be moved onto `estimate_request` so there is one call
site rather than two summations — the numbers do not change, only where they are
added up.

The window is resolved with `get_model_context_length` and cached on the run for
the life of the turn, falling back to `settings.context_window_size` when the
gateway cannot say. It is fetched lazily — only when a truncation actually
happens — so the normal path pays nothing for a guard it never reaches.

**Alternative rejected:** compact and then continue. Compaction summarises
completed jobs, so it cannot touch the current turn's messages, which are exactly
what grew. It would burn a summarisation call and change nothing about the
request that just truncated.

## Decision 6: making the seam visible

A new durable job event, `turn_continued`, persisted **and** published with the
durable row's id — the same pattern every other event in this module uses, and
for the same reason: the SSE stream both polls `list_events` and forwards the
bus, so a live copy published under an id of its own renders twice.

Payload: `reason` (always `"output_token_limit"` today), `finish_reason` (the raw
provider value, unnormalised, because that is the evidence), `continuation` (1-
based), and `max_continuations`.

`job_events.event_type` is `VARCHAR(64)` with no enum and no check constraint, so
this needs **no migration** — which also keeps this change clear of DRA-38's
`0013`.

The partial output is not at risk. The streaming callback has already appended a
`model_output` event for it before the round returns, and the next round opens a
*new* `model_output` event because the accumulators are re-initialised per
iteration. The transcript therefore reads: partial output → `turn_continued`
marker → continued output.

Replay does need a change, though, and this is the one place the "no migration,
no consumer changes" story does not hold. `session_transcript.py` replays each
`model_output` as its own assistant message and ignores event types it does not
know, so without a branch the model would be shown two adjacent assistant
segments with no account of why the first stops mid-sentence — and would be free
to conclude it had changed its mind. The branch flushes the current round and
appends a short note, following the precedent of the synthetic note the
`"interrupted"` job status already produces.

The job's `result_text`, however, would otherwise be only the final segment. The
continued segments are accumulated and joined so `complete_job` receives the
whole answer. They are joined with no separator, because a continuation resumes
the same text — the same reason the streaming client joins its chunks with `""`.

**Alternative rejected:** extend the existing `model_output` event in place so the
turn reads as one unbroken answer. That is the dishonest option. The user must be
able to see that the service resumed the turn rather than the model producing one
long response, and a seam that is invisible in the transcript is a seam that is
invisible in a bug report.

## Risks

- **A model that truncates every time.** Bounded at three continuations, then the
  turn completes and the user is back to the current behaviour. It cannot loop.
- **A provider that reports `length` when it means something else.** The cost is
  up to three extra calls on a turn that was already finished, and the
  `turn_continued` events say plainly what happened and why. Mitigated further by
  the kill switch.
- **A gateway that reports no stop reason at all.** Nothing changes for it; the
  turn completes as it does today. This is the intended degradation, not a gap.
- **Truncation inside a tool call's arguments.** Out of scope, and stated as a
  non-goal: those rounds carry tool calls, so the loop continues on its own and
  the existing `{"raw": "<partial json>"}` fallback produces a tool error the
  model recovers from. The stop reason is captured on the response either way, so
  a future change can act on it without re-plumbing the client.
