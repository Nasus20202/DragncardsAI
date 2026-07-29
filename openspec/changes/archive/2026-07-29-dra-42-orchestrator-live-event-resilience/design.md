## Context

Four unguarded Valkey call sites, one transient error class, four distinct
user-visible failures. Three are in the report's tracebacks, which name their frames
precisely, so those needed no diagnostic guesswork; the fourth came out of auditing the
remaining subscriber reads. The design work was almost entirely in choosing *what
degraded behaviour is correct* at each site, and in not buying resilience at the price
of silence.

The one fact everything below rests on: **for every publish in the job runtime, a
durable `job_events` row already exists, and the SSE stream polls that table as well
as forwarding the live bus.** A dropped publish therefore costs latency, not data.
There is exactly one exception, `compaction`, handled explicitly below.

## Decision 1: a decorator, not a guard at each call site

`publish` is typed to return `LiveJobEvent`, so swallowing inside it forces the
return type optional and, on paper, touches every caller. Three options were
weighed.

*Guard at each call site.* Rejected. There are around twenty publishes across
`prompt_run.py`, `builtin_tools.py`, `compaction.py`, `worker.py` and
`api/routers/jobs.py`. Twenty `try`/`except` blocks is twenty chances to forget one,
and forgetting one leaves exactly the defect being fixed. Several call sites already
have a guard around `append_event` *and* `publish` together, which proves the habit
is not reliably applied.

*Swallow inside `ValkeyLiveEventBus.publish`.* Rejected, for two reasons. It makes
the tolerance a property of one bus implementation rather than of the runtime, so
whether a job survives a Valkey blip depends on which bus was injected — and the
worker is constructed directly in tests and could be elsewhere. It also puts the
change in the exact lines DRA-37 is rewriting.

*A `BestEffortLiveEventBus` decorator.* Chosen. It states the property once — "in
this service, publishing is best-effort" — enforces it structurally, centralises the
log discipline so the streak counter has one home, and lives in a new file that
nothing else is rewriting. `LiveEventBus.publish` becomes `LiveJobEvent | None`; no
caller in the service reads the return value, and the type now says out loud that a
publish is not a guarantee.

It is applied twice, idempotently: in `create_app`, because everything in the running
process reads `app.state.live_event_bus` (worker, API routers, SSE stream), and in
`WorkerService.__init__`, because the guarantee about jobs must not depend on going
through the app factory. Being idempotent is what makes double-wrapping safe and
keeps one failure streak rather than two.

The readiness probe in `meta.py` asks `isinstance(bus, (ValkeyLiveEventBus,
InMemoryLiveEventBus))` — it wants to know which bus is configured, not whether it is
wrapped — so it unwraps first via `unwrap_live_event_bus`.

## Decision 2: the degraded poll cadence, and why it is the real trade-off

This is the one decision in the change with a genuine cost either way.

A healthy stream leans on the live bus and treats the Postgres poll as a backstop,
which is why the block timeout can be long — DRA-37 raises it to 15 s and measures
75× fewer commands per idle stream. When the live bus is down that relationship
inverts: the poll becomes the *only* source, and its interval becomes the
transcript's latency.

Both obvious answers are wrong:

- **Keep the healthy block.** A degraded stream would lag by a full 15 s. Degrading
  must not make the product feel worse than a hard failure would have felt honest.
- **Retry immediately.** A failing command fails fast — there is no blocking read
  left to pace the loop — so the loop becomes a hot spin, hammering Valkey and
  Postgres precisely while Valkey is unhealthy.

Chosen: `LiveBusDegradation` starts at **0.5 s**, doubles per consecutive failure,
and caps at **5.0 s**; the first successful read resets it and the stream returns to
the long block. The reasoning behind each number:

- 0.5 s keeps the transcript reading as live during the brief resets that this
  environment actually produces, which is the common case.
- Doubling bounds what a long outage costs: sixty seconds of continuous failure is
  about fifteen iterations, not a hundred and twenty.
- The 5 s ceiling sits well below the healthy 15 s block on purpose, so degradation
  never *increases* latency versus healthy operation — a degraded stream is at worst
  three times fresher than an idle healthy one.
- Resetting on the first success is what preserves DRA-37's saving. A stream that
  saw one blip an hour ago must not still be polling every half-second.

The retry attempt doubles as the reconnect probe, so the cadence governs both.

## Decision 3: retry the subscriber, never replace it

The brief asked for "re-subscribe with backoff". Reading the code, re-subscribing is
not a thing worth doing here, and this is worth stating rather than quietly omitting.

`RespConnection` opens a fresh TCP connection per command, so a
`ValkeyLiveEventSubscriber` holds no socket — there is nothing to rebuild. Its only
state is `_last_id`, advanced solely on a successful read, so a failed read leaves
the cursor exactly where it was and the next attempt resumes precisely. Retrying *is*
reconnecting.

Constructing a replacement would be strictly worse: a new subscriber starts at `0-0`
and replays the entire retained stream, re-delivering up to 512 entries the client
already has. Some carry `stream: True` snapshot ids, so replay is not merely wasteful.

## Decision 4: terminal detection must survive the degradation

The first draft of the guard swallowed the error and `continue`d, which introduced a
worse bug than the one being fixed: terminal detection lives only on the subscriber's
*timeout* path, so a job that finished while the bus was down would leave its stream
open forever. Instead a failure sets `live_event = None` and falls through, taking
exactly the path a timeout takes — check the job, drain trailing durable events,
close. `test_stream_still_closes_on_a_terminal_job_while_the_bus_is_down` pins it.

## Decision 5: audit the remaining subscriber reads, and guard the one that was missed

The brief named three sites. Enumerating every `subscribe` / `.get` in the service
turned up a fourth that no traceback in the report reached, and it is the one whose
name matches the issue title.

`resolve_child_outcome` — the body of `wait_for_subagent` — subscribes to the child's
live events and reads them through `_next_event`, unguarded. A reset there escaped the
wait, escaped tool dispatch, and landed in the *parent* job's handler. So a blip on one
job's event stream failed a different job, and specifically the orchestrating parent.
Two properties make this the most damaging of the four: it is the multi-agent path, and
the correct fallback was already implemented and simply bypassed — the child's row has
been the authority for this wait since the subagent-crash work, so the code needed a
`try` and nothing else.

The guard reuses `LiveBusDegradation`, which gives the same backoff for free, and
`continue`s into the existing row re-read. The absolute deadline is untouched, so a
degraded wait still cannot hold a parent hostage.

The audit's other finding is a negative worth recording: `resolve_question_outcome`
(`ask_user`) deliberately does not touch the live bus at all — it polls the stored
question, because the answer arrives over HTTP that may land on another replica. So it
needed nothing, and there is no fifth site.

## Decision 6: do not reorder the terminal transitions

`record_failure` is `append_event` → `publish` → `mark_job_failed`. Moving
`mark_job_failed` ahead of the publish was considered as defence in depth, and
rejected:

- It is unnecessary. Once `publish` cannot raise, `mark_job_failed` is always
  reached, so the ordering has no failure mode left to defend against.
- It is not free. DRA-37's stream-close shortcut rests on Postgres append always
  preceding the Valkey publish at every terminal path. The move would keep that
  particular invariant intact — `append_event` still comes first — but it changes the
  window in which a stream can observe a terminal status, and buying nothing at the
  price of perturbing a concurrent change's correctness argument is a bad trade.

So the ordering is untouched, everywhere. The terminal-status guarantee is delivered
by the publish being unable to throw, which is what the tests assert.

## Decision 7: the `EXPIRE` guard, and its short life

On the current tip `ValkeyLiveEventBus.publish` issues `XADD` then `EXPIRE`. The
report's second traceback names `EXPIRE` — so the event *was* in the stream and every
subscriber would have seen it, and the publish threw anyway. The guard logs one
warning without a stack and returns the event.

One line per occurrence needs no de-duplication, and that is a claim about
reachability rather than optimism: `EXPIRE` can only fail after `XADD` succeeded,
which means Valkey was reachable a moment earlier. A sustained outage fails at `XADD`
and never reaches this line at all.

**This guard is deliberately short-lived.** DRA-37 collapses the pair into a single
`EVAL`, at which point the failure mode it addresses stops existing: an atomic
publish either lands or does not. The guard and
`test_expire_failure_after_a_successful_xadd_still_publishes` should be deleted in
that rebase, not carried forward — and nothing else depends on them, which is why the
guard is one contiguous block.

The argument for swallowing gets *stronger* after that change, not weaker. Today one
can say "the work had already succeeded when we threw". After DRA-37 a failed publish
means the event genuinely did not reach the stream — and the durable Postgres row
still exists, so the SSE poll delivers it late rather than never. That is the whole
justification for `BestEffortLiveEventBus`, and it does not depend on the publish
being two commands.

## Decision 8: what silence costs, event by event

Swallowing is the risky half of this change, so the tolerated set is deliberately
narrow and the cost of each is named.

- **Publishes with a durable twin** (every event in the job runtime except one, plus
  `user_question_answered` from the API): the SSE stream's `list_events` poll yields
  the row. Cost: sub-poll-interval latency. Nothing else.
- **`compaction`**: the only publish with no `job_events` twin, by design — its
  summary's durable home is the compaction job created alongside it, not a row on the
  job being compacted. Dropping the live copy means the running transcript shows the
  summary only after the session is reloaded. That is a real cost, and it was weighed
  against the alternative, which is failing the job that was mid-compaction; the
  session then loses the turn *and* has no summary. Degrading is clearly better, and
  the drop is logged.
- **The TTL refresh**: at worst a live-event stream for a job that has stopped
  producing events expires early. Subscribers of a live job keep refreshing it.
- **A subagent's terminal event, to its waiting parent**: the wait re-reads the child's
  row every `SUBAGENT_WAIT_POLL_INTERVAL_SECONDS` (5 s by default), so the parent
  resumes up to one poll interval later than it would have. The absolute wait budget is
  unchanged, and the outcome the parent is told is identical because it comes from the
  row either way.

Nothing else is newly tolerated. Every Postgres write still raises, including
`append_event` — the durable row is the thing being relied on, so a failure to write
it must remain a failure. `XADD` still raises out of `ValkeyLiveEventBus`; only the
layer above, which knows the durable row exists, decides to tolerate it.

## Decision 9: log volume, at delta rates

DRA-35 set the discipline: one traceback per outage, counted warnings after it, a
recovery line. It applied that to a loop paced by a 0.5 s–30 s sleep, where one
warning per retry is bounded.

A publish is not paced by anything. It happens once per streaming delta — hundreds
per model response — so "one warning per failure" would trade a crash for a flood,
which is precisely what DRA-35 forbids. `FailureStreak` therefore logs the first
failure with a traceback and subsequent ones only when the count reaches a power of
two. A streak of 20,000 costs about fifteen lines; a streak of three costs two. The
end of a streak is always reported with its length, so an outage is visible as an
interval and not merely as noise. `test_failure_streak_logs_one_traceback_then_powers_of_two`
pins the shape.

## Risks

- **Silence is the standing risk of this change.** Mitigated by keeping the tolerated
  set to two named cases, by always logging, and by never touching a Postgres write.
  The residual exposure is a `compaction` summary that arrives on reload instead of
  live.
- **A rebase onto DRA-37 is expected.** The design pushes the new logic into
  `live_event_resilience.py` and touches `live_events.py` and `job_event_stream.py`
  in single contiguous hunks, so the rebase is a merge rather than a rewrite. The
  `EXPIRE` guard and its test are the one piece intended to be deleted rather than
  merged.
- **No in-memory state is introduced.** `LiveBusDegradation` belongs to one
  `stream()` call and dies with it. `FailureStreak` inside the bus wrapper is a log
  de-duplication counter on a long-lived singleton, the same category as DRA-35's
  streak counter on the ingest loop; losing it costs one redundant traceback and
  nothing else. Neither is state the service would want back after a restart.
