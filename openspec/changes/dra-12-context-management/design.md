# Design — context management for chat sessions

This document exists because DRA-12 is a proposal, not an implementation. It
records the design decisions the proposal's two recommended changes imply, the
alternatives considered inside each one, the failure modes each introduces, and
the observable signal that would show each worked. Nothing here has been built.

## Scope boundary, stated once

The design deliberately changes **nothing about the message list handed to the
model on a turn whose request fits inside the model's context window**. No new
trimming layer, no default limits, no truncation of a retained tool result, no
change to `build_message_history`, `_select_recent_message_orders`,
`_select_recent_tool_exchange_orders`, or `_flatten_replay_items`. Everything
below is either inside the compaction path or inside the arithmetic that decides
whether to enter it.

## (A) Bound and checkpoint the compaction input

### The invariant to establish

Today the compaction request has no upper bound: it is the whole session's raw
history, in one user message, plus the previous summary
(`services/agent-orchestrator/src/agent_orchestrator/runtime/compaction.py:120-171`).
The design target is a single invariant, strong enough that the failure described
in the proposal becomes impossible rather than merely rarer:

> **The compaction request SHALL never be assembled larger than the model's
> context window allows, and its size SHALL NOT grow with total session length.**

Three mechanisms together produce it, in the order they should be applied.

### A1. Checkpoint: summarise from the previous compaction, not from session start

`perform_compaction` already loads the previous `CompactionRecord` and injects
`existing_compaction.summary_text` as a system message (`compaction.py:127-139`),
and then *also* re-reads every job from session start
(`compaction.py:120-124`, `after_job_id=None`). The previous summary is by
construction a complete account of everything up to
`covers_up_to_job_id` — that is what the compaction prompt demands of it
(`compaction.py:24-92`, "A future AI agent will use this summary as its ONLY
memory"). Reading the same span again raw is redundant with the summary that is
already in the request.

The change is to pass `after_job_id=existing_compaction.covers_up_to_job_id` when
a previous record exists, which is exactly what `build_message_history` already
does for replay (`runtime/session_transcript.py:88-93`). The per-compaction input
then covers one inter-checkpoint span rather than the whole session, and stops
growing.

**Alternative considered and rejected:** keep the full re-read but drop the
previous summary from the request. That preserves "always summarise from raw" and
avoids summary-of-summary drift, but it keeps the unbounded growth that is the
actual defect, and it makes each compaction strictly more expensive than the
last. Rejected.

**Risk this introduces, and the mitigation.** After A1, the previous summary
becomes the only representation of anything before the last checkpoint, so
compression error compounds across compactions — a state fact the Nth summary
dropped is gone from the (N+1)th. Two things bound the damage. Raw `JobEvent`
rows are never deleted
(`openspec/specs/agent-orchestrator/spec.md:695`), so the information still
exists in Postgres and a from-scratch re-summarisation is always possible. And
the manual endpoint is the natural place to keep that escape hatch: **`POST
/sessions/{id}/compact` should gain an explicit "summarise from session start"
mode, and auto-compaction should always use the checkpointed mode.** That keeps
the cheap path automatic and the expensive path available when a user believes the
summary has lost something.

Whether the drift is bad enough to need more than that is the one genuinely open
question in this design. What is known: the compaction prompt is already written
for recursive use, it is already handed the previous summary today, and no
observed defect is attributed to summary drift. What would settle it: compact the
same long session twice under both modes and diff the summaries for dropped
state — hero HP, threat, villain phase, cards in play — which is cheap to do once
the checkpointed mode exists and is listed as a task.

### A2. Cap what a single tool event contributes

Independent of the checkpoint, one pathological tool result can dominate a span.
`history_text_parts` interpolates the complete `arguments` and `result` dicts
(`compaction.py:151-160`) with no bound. Add a per-event character budget, applied
to the argument text and the result text separately, with an explicit marker where
text was cut — `… [truncated, N chars omitted]` — so the summariser is told it is
reading a fragment rather than silently misled.

The proposal argues (and this design accepts) that truncation is defensible here
and not in replay: the reader is a summariser being asked for the gist, and a
marker is information. A retained *replay* result must never be truncated,
because the game agent cannot distinguish "absent from the board" from "cut off".

**The budget must be measured, not guessed.** A full simplified Marvel Champions
board is the payload that must survive intact: `SimplifiedGameState` is
`roundNumber`, `mode`, `villainHitPoints`, `stepId`, `stepDescription`, `players`,
and `zones` of `SimplifiedCard` records of seven fields each
(`services/game-service/src/game_service/api/models.py:94-119`). At roughly 120
characters of JSON per card and a realistic 60-120 visible cards, that is on the
order of 10-15 KB. A starting default of **20 000 characters** therefore sits
above a full board and below the payloads that actually need cutting — a
multi-card `search_cards_marvel_champions` result, a `load_cards` response. The
implementation task is to instrument the real per-tool character lengths across
one full game and confirm the default sits above the 99th percentile of
`get_game_state` before merging; if it does not, the default moves, not the
mechanism.

### A3. Total ceiling: drop oldest-first until the request fits

A1 and A2 make the input bounded in the normal case but do not *guarantee* it: a
single inter-checkpoint span can still be enormous if many turns ran between
compactions. So after assembling the history text, estimate the whole
summarisation request with the existing
`estimate_tokens_for_messages` (`runtime/tokens.py:29-62`) — the function
`compaction.py:12` already imports and never uses — and while it exceeds
`window × CONTEXT_COMPACTION_THRESHOLD`, drop history entries from the **oldest**
end.

Oldest-first is the right end for two reasons: the previous summary already covers
older material at least in outline, and the compaction prompt's own priorities are
current state and recent activity. Record how much was dropped on the log line and
in the emitted `compaction` event payload, so a summary produced from a partially
dropped span is identifiable afterwards rather than indistinguishable from a
complete one.

**Alternative considered and rejected:** map-reduce summarisation — summarise
halves, then summarise the summaries. It preserves more, and it costs two or more
LLM calls inside a path that is already blocking the user's turn, with a second
new failure mode (a partial map result). Rejected as disproportionate to a case
that A1 makes rare; revisit only if the drop counter from A3 turns out to fire
regularly, which is exactly what recording it is for.

### A4. A compaction failure must not fail the user's turn

`maybe_auto_compact` is awaited unguarded at `runtime/prompt_run.py:207`, inside
the `try` whose handlers at `:567`/`:578` mark the job failed. Wrap the call so
that any exception is caught, logged with the ratio that triggered it, recorded as
a transcript-visible event, and followed by the turn proceeding on the history it
already has.

Two sub-decisions:

- **`ValueError` is not a failure.** `perform_compaction` raises `ValueError` for
  "No completed jobs to compact" and "No history content to compact"
  (`compaction.py:111`, `:163`). Both mean "nothing to do", and both are reachable
  on an early turn. They should be logged at debug/info and never surface to the
  user. Only a provider or persistence failure warrants the event.
- **A new event type costs a dashboard edit.** Emitting `compaction_failed`
  requires adding it to `STREAM_EVENT_TYPES`
  (`services/dashboard/features/play/lib/play-session-events.ts:63-79`), because
  `use-job-streaming` registers one named `EventSource` listener per entry with no
  `onmessage` fallback and silently drops anything absent
  (`services/agent-orchestrator/AGENTS.md:44-46`). No migration is needed —
  `job_events.event_type` is a free string. If the owner would rather not add a
  transcript element, the fallback is log-only, which still fixes the turn
  failure; the event is what makes the degradation visible rather than silent, and
  is preferred.

**Ordering note for whoever implements this:** A4 is the smallest patch of the
four and is what converts a turn failure into a degraded turn. A1-A3 are what
stop the failure happening. If (A) has to be split, A4 ships first.

## (B) Make the trigger measure the request it protects

### What changes arithmetically

`maybe_auto_compact` today estimates only `build_message_history`
(`prompt_run.py:857-860`). It should estimate the same four components the worker
is about to send:

1. the system prompt already built at `prompt_run.py:156-166`,
2. the tool definitions already resolved at `prompt_run.py:180-204` (built-ins
   plus MCP), via the existing `estimate_tokens_for_tools`
   (`runtime/tokens.py:79-83`),
3. the replay, as today,
4. the current turn's user message **as rendered** — the output of
   `render_prompt_with_inline_skills` (`runtime/skills.py:195-232`), which is
   where DRA-15's inlined `SKILL.md` content lives.

Components 1, 2 and 4 are the "fixed cost" of the turn: they do not depend on the
replay and compaction cannot reduce them. Component 3 is the only part compaction
shrinks.

### Sequencing

The worker already computes the system prompt and the tool list *before* calling
`maybe_auto_compact` (`prompt_run.py:156-207`), so only the rendered user message
has to move: hoist the `render_prompt_with_inline_skills` call from
`prompt_run.py:224-228` to above the auto-compaction call, and pass the fixed-cost
estimate in. The prompt event emission and the `skill_loaded` announcements at
`prompt_run.py:230-233` stay where they are — only the render moves, so the
transcript's ordering is unchanged.

Deliberately *not* done: assembling the full message list, measuring it, and then
compacting and rebuilding. That would measure exactly the right thing and would
build the replay twice on every turn, which is the expensive part
(`list_completed_jobs_for_replay` loads every prior job with its events). The
fixed-cost-plus-replay sum is the same number without the second reconstruction.

### The failure mode this introduces, and the guard it needs

This is the part of (B) that must not be skipped. Once fixed costs count toward
the ratio, a session can sit above the threshold *with an empty replay* — a large
resolved game-service tool catalog plus a large system prompt plus a mentioned
32 KB `SKILL.md` can approach `0.8` of a small model's window on its own. Naively
implemented, that session would attempt compaction on **every turn**, each attempt
an extra blocking LLM call that cannot possibly reduce the ratio, because
compaction only shrinks component 3.

So the trigger must be: compact when the total ratio reaches the threshold **and**
the replay is large enough for a summary to plausibly be smaller than it. A
concrete, defensible form: require the replay estimate to exceed the token cost of
a summary — the running mean of `CompactionRecord.tokens_used` for the session, or
a fixed floor on the first compaction. When the total is over threshold but the
replay is under the floor, log once per job that compaction was skipped because the
pressure is fixed cost, not history. That log line is also the diagnostic that
tells the owner the real problem is the tool catalogue or the model choice, which
no amount of compaction will fix.

### Why the threshold stays at 0.8

The point of (B) is to measure correctly, not to compact more, and the two must
not be conflated. Correcting the measurement already moves the effective trigger
earlier in wall-clock terms — a session whose fixed costs are 15k tokens now
reaches `0.8` roughly 15k tokens of replay sooner. Lowering the threshold on top
of that would compound a change whose magnitude has not been observed yet. If
`0.8` proves too tight once the number is honest, it is one env var
(`CONTEXT_COMPACTION_THRESHOLD`, `config.py:125-130`) and a separate decision.

### Why this needs its own sign-off

(A) makes an existing mechanism work as intended. (B) changes *when* the model's
history is summarised, which changes what the model sees on some turns — earlier
compaction means a summary standing in for turns that would previously have been
replayed verbatim. That is precisely the class of change the issue says must not
be guessed at, and it is the one place this proposal is not merely fixing a fault.
It is recommended, with the reasoning above, and it is separable: (A) can be
approved and merged without it.

## (C) Say what the limit fields will drop

The two fields in the config drawer
(`services/dashboard/features/play/components/play-config-panel.tsx:250-266`) are
bare integers with the placeholder "Unlimited". Nothing tells the user that
setting the tool-exchange limit keeps the newest board-state result and discards
older ones (`runtime/session_transcript.py:390-421`), or that the message limit
counts conversational messages only and never the compaction summary
(`openspec/specs/agent-orchestrator/spec.md:493`).

One line of helper text under each field, following whatever pattern
`TextInputField` already supports in that panel. No spec delta: the dashboard spec
requires the fields to exist and does not constrain their labels. This rides along
with (B) rather than justifying a change of its own.

## How each part would be known to have worked

| Part | Signal that it worked | Signal it did not |
| --- | --- | --- |
| A1 checkpoint | Estimated compaction-input tokens are roughly constant across successive compactions in one long session, instead of rising monotonically | Input size still tracks total session length |
| A1 drift risk | Diff of checkpointed vs from-scratch summaries of the same session shows no dropped tracked state (HP, threat, villain phase, cards in play) | Checkpointed summary omits state the from-scratch one keeps |
| A2 cap | No `get_game_state` result is ever truncated in a real game; oversized card-search results are, with the marker present | A board state gets cut, i.e. the default is too low |
| A3 ceiling | The assembled compaction request never exceeds `window × threshold`; the drop counter stays at zero in normal play | Drops fire routinely, which is the trigger to reconsider map-reduce |
| A4 guard | A session with a deliberately failing provider call completes its turn with a `compaction_failed` event instead of a failed job | The job still fails |
| B measurement | The ratio in the auto-compaction log line and the ratio the context widget shows agree for the same session at the same moment; no request is ever sent above the window | The two still disagree, or a turn still overflows |
| B guard | A session whose fixed costs alone exceed the threshold logs the skip once per turn and makes no compaction call | Repeated compaction attempts that do not lower the ratio |
| C | A user setting a tool-exchange limit can state, unprompted, that the newest board state is kept | — |

Two of these are measurable only against a real long game, not a unit test:
A1's constancy and B's agreement with the widget. Both are cheap to observe from
the existing INFO log line at `prompt_run.py:868-874` once it reports the
components, and that log line should report them.

## Things this design will not do, restated so no one adds them later

- No default value for `context_recent_message_limit` or
  `context_recent_tool_exchange_limit`. The proposal explains the deferral and its
  precondition.
- No truncation of any tool result that reaches the model.
- No second summarisation mechanism alongside `CompactionRecord`.
- No new table, column, or migration. `compaction_records.covers_up_to_job_id`
  already exists
  (`services/agent-orchestrator/src/agent_orchestrator/schema_migrations/sql/0002_context_management.postgresql.sql:5-12`)
  and is the only durable thing (A) needs. Nothing is held in memory across
  requests.
- No change to the judge, the eval service, or the history service. DRA-10's
  round-scoped judge context is a different consumer with a different ceiling, as
  the proposal sets out, and nothing here touches it.
