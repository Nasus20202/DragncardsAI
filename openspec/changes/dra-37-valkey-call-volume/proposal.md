# The live-event path stops spending a Valkey command per token and per 200ms

## Why

DRA-37 reports, in the reporter's words: *"Agent orchestrator trace have over 6K
span, with thousands of Valkey calls. We could optimize this."*

Two different defects fit that description and they need different fixes, so the
first thing this change did was separate them by measurement rather than by
argument.

**(a) Too many commands are genuinely issued.** Confirmed, and it dominates.
Read straight off the running stack's `agent-orchestrator-valkey` after 15,760
seconds of uptime: **40,442 commands processed, of which ~416 (1.0%) did any
work.** The other 99% is three idle poll loops. Within agent-orchestrator's own
traffic the loop is the SSE job-event stream, which spent **5 Valkey commands and
10 PostgreSQL queries per second, per open stream, for the entire life of a job**
— because its blocking-read timeout was wired from `worker_poll_interval_seconds`
(0.2s), a value tuned for how fast the worker claims a queued job from PostgreSQL
and meaningless as a stream block. A stream held open for the ~7 minutes of one
agent turn therefore contributes ~2,000 `valkey.execute` spans and ~4,000
database spans to **one** trace. That is the reported 6K.

**(b) Too many spans are emitted per command.** Real, but it is not an
independent defect — it is an exact mirror of (a), and treating it as the bug
would have been the wrong fix. Measured through the real RESP client with the
socket faked, for every scenario tried: **commands = TCP connections =
`valkey.execute` spans, 1:1:1, with no amplification anywhere.** The live stack
agrees to three decimal places — 40,454 connections received against 40,442
commands processed. So "6K spans" and "6K commands" are the same number said
twice, and there is no span-level measure that reduces the spans without leaving
the commands, and the connections, exactly where they were. Sampling here would
have deleted the evidence and kept the cost.

That also settles the hypothesis that `6a4972e` (DRA-23) was a regression
boundary: it began injecting a tracer, so it is why the volume became *visible*,
but the 1:1 measurement shows it changed nothing about the volume itself.

The three call-site defects behind (a), all in agent-orchestrator:

1. **The SSE stream's fallback interval was the worker's job-claim tick.** 5
   commands/second/stream while nothing happens.
2. **Publishing one live event cost two commands.** `XADD` then a separate
   `EXPIRE` to re-arm the stream TTL. A streaming model publishes one live event
   per token, so this doubled the busiest path in the service.
3. **A subscriber read one entry per command.** `XREAD ... COUNT 1` made the
   consumer issue as many commands as the producer, so every viewer of a
   streaming job added the producer's command rate again.

## What lengthening the interval exposed, and why it is the larger half

Making the fallback interval long is only safe if nothing a user waits on depends
on it. Several things did. The 0.2s poll had quietly become a delivery mechanism
in its own right: any event persisted with no matching `publish` reached the
client only when that poll next ran, and at 200ms nobody could tell. DRA-34 had
even relied on this in writing, removing both `cancellation` publishes on the
explicit grounds that *"the stream's own poll — 200 ms by default — delivers
it."*

So every durable append in the service was audited against its publish. Three
classes came out.

- **Terminal, and so able to hang the UI.** Three sites append a `cancellation`
  with no publish — `request_cancel`, for the job *and* for each active child, and
  `mark_job_cancelled`. `cancellation` is terminal, so until it is *delivered* the
  client's stream does not close: a user clicking cancel would watch the
  transcript sit there for up to 15 seconds. For a **queued** job it is worse than
  it first looks, because `request_cancel` cancels it outright and the worker never
  runs it, so that one append is the only announcement that will ever exist.
- **Frequent, and so able to make a running agent look frozen.** `tool_call` and
  `tool_result` were **never published at all**, by any path. A tool call is
  recorded *before* the tool runs, and a slow tool is exactly when the live bus
  falls quiet — so the transcript would show nothing for the duration of the call.
  This is what the 200ms poll was really covering.
- **Cosmetic.** Two `progress` rows. The queued one is read by the stream's first
  database pass before it ever waits, so it is not delayed at all; the running one
  is, and is left that way deliberately.

The fix for the first two is to publish, not to shorten the interval — which
keeps the 75× reduction and leaves the service with a live bus that actually
carries the events a client is waiting for.

## What Changes

- **agent-orchestrator (SSE job-event stream)** — the idle fallback interval
  becomes its own setting, `JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS`, defaulting to
  15 seconds instead of inheriting 0.2. It is a fallback, not a latency budget: a
  published event ends the wait immediately, so nothing a client sees arrives
  later. Following the audit above, what remains behind it is one cosmetic
  `progress` row.
- **agent-orchestrator (cancellation delivery)** — `mark_job_cancelled` returns
  the id of the `cancellation` row it appended and `request_cancel` returns one
  per affected job, so their four callers can publish the live copy under the
  durable row's own id. That restores instant delivery *and* keeps DRA-34's
  id-collapse, so the cancellation still renders exactly once. A bare `publish()`
  would have re-introduced the duplicate DRA-34 fixed.
- **agent-orchestrator (tool events)** — `tool_call` and `tool_result` are now
  published as well as persisted, with the durable id, at all four sites
  (including the invalid-call path). No dashboard change is required: both types
  are already on its SSE allowlist and it de-duplicates on the payload id, so the
  live copy and the polled copy collapse into one transcript row.
- **agent-orchestrator (stream close)** — once the terminal event has been
  delivered from the database the loop makes its final database pass instead of
  waiting on the live bus first. Without this, lengthening the interval would
  have turned closing such a stream into a visible 15-second hang; with it, that
  close is now faster than it was before the change.
- **agent-orchestrator (publish)** — appending an event and re-arming its
  stream's TTL become a single scripted round trip. The two operations, their
  order and the returned entry id are unchanged; only the number of round trips
  is. The TTL still has to be re-armed on every append, because a job quiet for
  longer than the TTL would otherwise lose its stream mid-run and the next append
  would recreate the key with no expiry and leak it.
- **agent-orchestrator (subscribe)** — `XREAD` asks for up to 64 entries and the
  surplus is held inside that one subscriber until it is asked for them. `get()`
  still hands back one event at a time, so no caller changes. The buffer is
  request-scoped — a subscriber lives for exactly one SSE request or one subagent
  wait — and holds entries already taken off the stream, so it is not
  process-lifetime cached state.
- **observability spec** — the existing requirement that a polling loop be traced
  per batch rather than per iteration is stated to also govern dependency spans,
  and the resolution of a loop that is too chatty is stated to be reducing the
  commands rather than suppressing or sampling the spans. Both are what this
  change did; neither was written down, and the two existing requirements could
  be read as contradicting each other.

Measured effect, same harness before and after, counting commands the real client
put on a faked wire:

| | before | after | |
|---|---|---|---|
| Idle SSE stream, per second per stream | 5.0 | 0.067 | **75× fewer** |
| Publish 100 live events | 200 | 100 | **2× fewer** |
| One 500-delta turn, 1 viewer | 1,500 | 508 | **2.95× fewer** |
| One 500-delta turn, 2 viewers | 2,000 | 516 | **3.88× fewer** |

Commands, TCP connections and spans move together in every row, before and
after, because they are the same quantity.

The publishes added by the audit cost one command each — two per tool round and
at most two per cancellation, so about ten on a five-round turn, against the 508
above. That is a ~2% give-back for removing the reason the poll had to be fast.

## Capabilities

### Modified Capabilities

- `agent-orchestrator` — the live-event bus's per-event and per-read command
  cost, and the SSE stream's idle fallback interval and close path. Also DRA-42's
  "a failing event-stream TTL refresh does not undo a published event", restated
  as an atomicity requirement: the single-command publish makes the partial
  failure that requirement tolerated impossible rather than tolerated.
- `observability` — how per-command dependency spans on a polling loop are to be
  brought under control.

## Impact

- **Production code** — `runtime/live_events.py` (batched read, single-round-trip
  publish), `runtime/job_event_stream.py` (own interval, close without waiting),
  `config.py` (new setting and its validator), `runtime/app.py` (wiring),
  `repositories/jobs.py` (both cancellation writers return the id they appended,
  via a new `AppendedCancellation`), `runtime/prompt_run.py` (publish the two
  cancellations and the four tool-event rows), `api/routers/jobs.py` and
  `api/routers/sessions.py` (publish what `request_cancel` appended).
- **Configuration** — `JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS` added to
  `services/agent-orchestrator/.env.example`. No compose change: the default is
  correct for every environment and nothing overrode the old value.
- **Tests** — orchestrator unit tests asserting the command *counts* rather than
  only the behaviour: publish costs one command and carries the key as a declared
  `KEYS` entry, the optional `durable_event_id` travels inside that same one
  command and reads back, three events arrive on one read and the next read
  resumes from the last entry handed out, the buffer is dropped with the
  subscription, and the new setting is independent of the worker tick. Plus
  latency tests for the interaction the audit found: a stream whose terminal event
  came from the database closes without waiting the interval, a cancellation
  reaches an open stream under an interval *longer than the test's own timeout*
  (so it fails rather than merely slows if the publish is dropped), the run
  publishes the cancellation it persists under the durable id, and
  `request_cancel` returns an id per affected job. The cancellation test was
  mutation-checked: deleting the publish makes it fail. DRA-42's
  `test_live_event_resilience.py` is reconciled rather than rewritten — its
  stream tests take the renamed interval, and its two TTL tests are retargeted at
  the shape that now exists: no separate `EXPIRE` command is issued at all, and a
  failing append still raises for `BestEffortLiveEventBus` to absorb.
- **Documentation** — a "Valkey command volume on the streaming path" section in
  the agent-orchestrator README recording why these properties exist, since each
  is a one-line edit away from being undone by someone who does not know what it
  cost, plus the rule the audit produced: a durable event with no publish is now
  late by the idle interval, not by 200ms.
- **No database change and no dashboard change.** Two repository return types
  change (`mark_job_cancelled`, `request_cancel`), both internal. The SSE wire
  format, the event types and the ordering guarantees are untouched.

## Non-goals

- **No connection pooling or pipelining in the shared RESP client.** One TCP
  connection per command is the multiplier under all of this, and the fix is
  filed separately with DRA-35's measurements. This change is deliberately
  confined to the call sites, where the cost can be cut without touching a file
  three services share. See `design.md`.
- **No span sampling, no filtering of `valkey.execute`, and no removing the
  tracer from the RESP client.** The 1:1 measurement is the argument: every one of
  those would have hidden the symptom and kept the cost. They stay available for
  the day the command count is proportionate and still too voluminous to export,
  which is not today.
- **No throttling of the live publish itself.** The per-token publish is the
  product feature — it is what makes the transcript stream — and the neighbouring
  PostgreSQL write is already throttled 1-in-20 precisely so the Valkey publish
  does not have to be. Making the *event* cheaper is in scope; making the UI
  coarser is not.
- **No fix for history-service's ingest loop**, which by measurement is the
  single largest command producer on this Valkey (78.6% of all commands over 4.4
  hours) and issues two commands that do no work on every idle cycle. It is a
  different service on a different symptom, and its reclaim cadence is entangled
  with at-least-once delivery. Quantified in `design.md` and handed back for its
  own change.
- **No dashboard change**, though the dashboard is what multiplies this: one Play
  page opens one stream per running subagent plus a duplicate for an open
  subagent modal, so a 10-subagent fan-out holds 11-12 concurrent streams from a
  single tab. Reducing per-stream cost is this change; reducing stream *count* is
  a separate one. Recorded in `design.md`.
- **No change to the `agent_orchestrator.claim_next_job` span**, which opens a
  root span every 0.2s and is therefore ~5 always-sampled traces per second per
  replica at idle. It costs no Valkey commands, so it is outside this issue even
  though it is the same mistake.
- **No publish added for the `progress {"status": "running"}` row.** It is the one
  durable event the audit deliberately leaves on the fallback poll: it is not
  terminal, so it cannot hold a stream open, and the same fact is already on the
  job row the dashboard renders from. It is late by up to the interval, and that
  is accepted rather than overlooked.
- **No move of the publish into the repository.** Making `append_event` publish
  would enforce "durable implies live" everywhere in one stroke and delete this
  whole class of bug, but it gives the repository a bus dependency, changes every
  repository test, and would publish events that were deliberately never
  published. It is the right shape and the wrong change to make inside a
  Low-priority optimisation; recorded in `design.md`.
