# Design

## How the diagnosis was made, and why it was made this way

The report gives one number ("over 6K span, with thousands of Valkey calls") and
two incompatible explanations fit it: the service really does issue that many
commands, or it issues a reasonable number and traces each one. Reasoning cannot
choose between those, so both were measured.

**Measurement 1 — the live stack, read-only.** `INFO commandstats` and `INFO
stats` on the running `agent-orchestrator-valkey` (host port 6381; Valkey 9.1.1),
after 15,760s of uptime:

```
total_connections_received : 40454
total_commands_processed   : 40442

xinfo|groups  10592     xread     5081     get     152
xautoclaim    10600     ping      3140     xadd     78     xack   77
xreadgroup    10592                        incr     47     setex  37
                                           del      24     expire  1
```

Two things fall out of this immediately.

- **Connections ≈ commands (40,454 vs 40,442).** The client opens one TCP
  connection per command, so command count, connection count and span count are
  one quantity, not three. This is the whole (a)-versus-(b) answer.
- **~416 commands out of 40,442 (1.0%) did work.** Everything else is three idle
  loops: the history-service consumer's triple (`xinfo groups` + `xautoclaim` +
  `xreadgroup`, 10,592 each — 78.6% of the total), the orchestrator's SSE `xread`
  (5,081 — 12.6%), and Docker's own healthcheck `ping` (3,140 — 7.8%). Note
  `xadd:78` against `expire:1`: barely any job ran during those 4.4 hours. This
  is the *idle floor*, not a busy period.

**Measurement 2 — commands per operation, through the real client.** A harness
replaces `asyncio.open_connection` with a fake socket that speaks minimal RESP,
so `dragncards_common.resp.RespConnection` runs unmodified and every command
counted is one the service would really have put on the wire. It also counts
spans, by passing a counting tracer. Result, for every scenario tried, before and
after: **commands = TCP connections = `valkey.execute` spans, exactly.**

| scenario | before | after |
|---|---|---|
| Idle SSE stream, per second | 5.0 | 0.067 |
| `publish` × 100 | 200 (`XADD` 100 + `EXPIRE` 100) | 100 (`EVAL` 100) |
| 500-delta turn, 1 viewer | 1,500 (1,000 publish + 500 consume) | 508 (500 + 8) |
| 500-delta turn, 2 viewers | 2,000 (1,000 + 1,000) | 516 (500 + 16) |
| `emit_agent_move` × 50 | 100 (`INCR` + `XADD`) | 100 — unchanged |

**Reconciling with the reported trace.** `start_span` inherits the ambient
context, so a long-lived SSE request's `valkey.execute` spans are all children of
that one request span. Per loop iteration the stream did one `XREAD` plus a
`list_events` query, and on a timeout a `get_job` query as well — about three
spans a tick, five ticks a second. **6,000 spans is therefore ~7 minutes of one
open stream on one running job**, of which about a third are Valkey. That matches
both halves of the report: "over 6K spans" and, as the minority of them,
"thousands of Valkey calls".

## Decisions

### The SSE fallback interval gets its own setting, defaulting to 15s

`JobEventStreamService` was constructed with
`poll_interval_seconds=settings.worker_poll_interval_seconds`. Nothing about the
worker's PostgreSQL job-claim latency has anything to do with how long a
client's stream should block on Valkey; the reuse reads as an accident, and it is
the direct cause of the reported trace.

What the interval actually governs, once you follow the loop: a published event
returns from `XREAD` immediately, so it is not a delivery latency. Every ordinary
terminal transition publishes — including the worker's last-resort failure guard.
The database fallback therefore only catches a job that went terminal with no
event reaching this subscriber. 15 seconds of extra latency on that path is not
perceptible, and the setting exists so it can be tuned without a code change.

- *Rejected: keep 0.2s and remove the tracer from the SSE connection.* Removes
  the spans and keeps 5 commands, 5 TCP connections and 10 database queries a
  second. Fixes the report and not the problem.
- *Rejected: 30-60s.* Tempting, and the difference from 15s is a factor of 2-4 on
  a number already reduced 75×. 15s keeps the degraded-path detection inside a
  human's patience with no measurable extra cost.
- *Rejected: derive it from the job's state (short while queued, long while
  running).* More branches on a hot loop to save a handful of commands during the
  seconds a job spends queued.

### Delivering a terminal database event no longer waits an interval first

Found while reasoning about the above, and it is what makes it safe. The loop
yielded a terminal event read from the database, then blocked on the live bus,
and only on that wait timing out did it check the job status and return. At 0.2s
nobody noticed. At 15s, closing such a stream would have hung for 15 seconds — a
regression the interval change would have introduced on its own.

The loop now continues straight to its final database pass when the terminal
event has already been delivered. It terminates in the iteration after, on the
existing `terminal_received and not events` guard. Closing is now strictly faster
than before the change, not merely no slower.

- *Rejected: return immediately on seeing a terminal event.* Would drop events
  persisted after the terminal one. The extra pass is deliberate and is kept.

This depends on an invariant that was checked rather than assumed, because the
shortcut would be unsafe without it: **every terminal path appends the event to
PostgreSQL before publishing it to Valkey.** Verified at all of them —
`complete_job`, the interrupt and `BifrostError` paths in `prompt_run`, the
cancellation paths, and the worker's last-resort crash guard. So a terminal event
seen on the live bus always has its database row already visible, and the
shortcut's final pass cannot return before that row is readable. If that ordering
is ever inverted, this shortcut has to be revisited.

That invariant is necessary but **not sufficient**, as the audit below found: it
says a published terminal event has a row, not that every terminal row is
published.

### The audit: every durable append, against its publish

Lengthening the interval is only safe if nothing a user waits on rides on the
poll. Auditing all 26 `append_event` call sites against the publishes beside them:

| Site | Event | Terminal | Published? | Action |
|---|---|---|---|---|
| `repositories/jobs.py` `enqueue_prompt_job` | `progress` (queued) | no | no | **none needed** — read by the stream's first database pass, before it ever waits |
| `repositories/jobs.py` `request_cancel`, the job | `cancellation` | **yes** | no | **publish** from both callers |
| `repositories/jobs.py` `request_cancel`, each active child | `cancellation` | **yes** | no | **publish** — each child may have its own open stream |
| `repositories/jobs.py` `mark_job_cancelled` | `cancellation` | **yes** | no | **publish** from both `prompt_run` cancel checks |
| `prompt_run.append_tool_call_event` | `tool_call` | no | **never, by any path** | **publish** |
| `prompt_run.append_tool_result_event` | `tool_result` | no | **never, by any path** | **publish** |
| `prompt_run.append_invalid_tool_result` | `tool_call` + `tool_result` | no | **never** | **publish both** |
| `prompt_run` progress-running | `progress` (running) | no | no | **left**, deliberately |
| `prompt_run` first `reasoning` / `model_output` row | streaming | no | yes, per delta | none |
| `prompt_run` final reasoning/output flush | streaming | no | yes, per delta | none |
| everything else (`completion`, `failure`, `skill_loaded`, `compaction_failed`, the `user_question` trio, the subagent events) | — | mixed | yes, with `durable_event_id` | none |

The severity ordering is not what the report suggested. The `cancellation` sites
leave a stream **open** — the user clicks cancel and nothing happens. The
`tool_call` / `tool_result` sites were never on the bus at all, and a tool call is
recorded *before* the tool runs, at precisely the moment the bus falls quiet; a
slow tool would leave the transcript blank for its whole duration. That second
class is the more frequent, and it is the one the 200ms poll was really carrying.

### Cancellation and tool events are published, rather than the interval shortened

- *Rejected: shorten the interval to ~2s instead.* Bounds every poll-only path at
  2s with no new publishes and no duplicate risk, and still cuts the reported trace
  ~10×. Rejected because it keeps the poll load-bearing — the next durable event
  somebody forgets to publish is silently late again — and gives back most of the
  win for a problem that has a direct fix.
- *Rejected: re-add a bare `publish()` for the cancellations.* Precisely what
  DRA-34 removed. It renders the cancellation twice: the stream serves both the
  live bus and `list_events`, the client de-duplicates on the payload id, and a
  live copy under a Valkey stream id does not collapse into the polled row. The
  durable id has to travel with it.
- *Rejected: give the repository the bus so `append_event` always publishes.* The
  shape that would delete this whole class of bug — "durable implies live" as an
  invariant rather than a per-site discipline. Not taken here: it gives the
  repository a bus dependency, touches every repository test, and would start
  publishing rows deliberately never published. Worth its own change.

So `mark_job_cancelled` returns the id of the row it appended — its two callers
never used the `Job` it used to return, so nothing else moves — and
`request_cancel` returns an `AppendedCancellation` per affected job, since it
writes one for the job and one for each active child and each of those may have
its own reader. Four call sites publish under those ids.

**Measured end to end, against the real Valkey**, rather than argued. Driving the
real cancel route, the real repository, the real `ValkeyLiveEventBus` and
subscriber and the real SSE generator, with the interval at the shipped 15s and
the job left queued so `request_cancel`'s append is the only announcement there
will ever be:

| | `POST /cancel` → cancellation on the wire |
|---|---|
| with the publish | **72 ms** |
| with the publish deleted | **14,144 ms** |

One durable `cancellation` row either way, and with the publish the frame carries
that row's id. So the regression was real, it was ~14s of a visibly hung UI, and
publishing closes it.

The tool events were worth checking rather than assuming, because adding a publish
where none existed is exactly how DRA-34's duplicate arose. Traced through the
dashboard: `upsertStreamEvent` in
`services/dashboard/features/play/lib/play-session-events.ts` is the only
de-duplication point and keys on the payload `id`; both `tool_call` and
`tool_result` are already on its SSE allowlist; so the live copy and the polled
copy arrive under the same id and collapse to one entry — and because the same
`payload` dict is handed to both `append_event` and `publish`, the comparison is an
identity-preserving no-op that does not even re-render. Pairing is by
`tool_call_id`, but de-duplication happens upstream of it on the id, so a duplicate
could only arise if `durable_event_id` were omitted, which is why all four sites
capture it.

### Publishing an event is one round trip, via a Lua script

`publish` did `XADD` then `EXPIRE`. Since `prompt_run.on_bifrost_delta` publishes
on *every* streamed reasoning and content delta, that doubled the cost of the
busiest path in the service. The neighbouring PostgreSQL write is throttled
1-in-20 (`db_write_interval = 20`); the Valkey publish is not, and should not be —
per-token publishing is what makes the transcript stream.

DRA-34 also added an optional `durable_event_id` stream field, so the script takes
the event's field/value pairs as a variable-length `ARGV` tail rather than as fixed
positions. That keeps one script for both shapes — no branch, no second script, and
the optional field costs no extra command.

`EVAL` performs the same two operations, in the same order, and returns the same
entry id, in one round trip. The key travels as a declared `KEYS[1]` rather than
interpolated into the script body, so the script is a constant and the key is
data. There is precedent in the repo: game-service already releases its session
lock with a two-command `EVAL` (`coordination/session_store.py`).

The TTL must be re-armed on every append, which is why this could not simply be
thinned out: a job publishing nothing for longer than the 300s TTL loses its
stream key, and the next append recreates it **with no expiry at all**, leaking
it. Delivery survives that expiry (stream ids are monotonic in wall-clock ms, so
a subscriber's stored last-id still works against a recreated key), but the leak
does not.

- *Rejected: refresh the TTL only every Nth publish.* Needs a counter or a
  last-refreshed timestamp per job, surviving across calls on a
  process-lifetime bus object. That is exactly the in-memory service state the
  repository forbids, and it would be a cache of coordination state at that.
- *Rejected: `EVALSHA` with a script cache.* Saves ~200 bytes per call and
  requires tracking whether this server has the script — process-lifetime state
  again, plus a `NOSCRIPT` recovery path. Not worth it when the alternative being
  replaced is a whole extra TCP connection.
- *Rejected: pipeline the two commands on one connection.* The right answer, and
  it is in `resp.py`. See below.

### A subscriber reads a batch and buffers the surplus

`XREAD ... COUNT 1` is the consumer-side mirror of the publish problem: one
command per event delivered, so every viewer of a streaming job re-added the
producer's command rate. `COUNT 64` with the surplus held in the subscriber
brings the consumer's traffic down to roughly one command per burst — measured, 8
commands to drain 500 events instead of 500.

`get()` keeps returning a single event, so `JobEventStreamService` and
`resolve_child_outcome` are unchanged. This also silently improves the subagent
wait, whose subscriber previously issued one `XREAD` per event a chattering child
emitted.

On the in-memory-state rule: the buffer is a field on `ValkeyLiveEventSubscriber`,
and a subscriber is created per SSE request or per subagent wait and closed with
it. It holds at most 64 entries already removed from the stream, for the duration
of one call — the request-scoped case the rule permits — not a process-lifetime
cache. `aclose()` drops it. The class already held `_last_id` on exactly the same
terms.

- *Rejected: change `get()` to return a list.* Every caller wants one event and
  would have to grow its own buffer. Same buffer, more places.
- *Rejected: a much larger `COUNT`.* 64 sits well under the 512-entry per-job
  stream cap, so no single reply can be large, and the marginal saving above 64 is
  negligible.

### Span-level measures are deliberately not taken

Sampling, a collector filter on `valkey.execute`, or withholding the tracer from
the polling connection would each have cut the reported number. The 1:1
measurement is the reason none were: the spans are a faithful report, and every
one of these leaves the commands and the TCP connections untouched while removing
the only signal that would show it. There is currently **no sampler configured
anywhere in the repository** — the SDK falls through to
`parentbased_always_on` — so these levers all remain available for the day the
command count is proportionate and still too voluminous to export. That day is
not today.

## Reconciling with DRA-42

This change was written before DRA-42 merged and rebased onto it afterwards. The
two touch the same three places, and what happens at each is a decision rather
than a merge outcome.

**The stream's live read — both guards stay, and they compose.** DRA-42 wrapped
`live_subscriber.get` in a `try/except Exception` that logs, backs off and sets
`live_event = None`, so a stream whose bus is down keeps serving durable events
instead of raising out of the response. DRA-37 added the terminal-close shortcut
immediately above that line. They do not conflict and neither is redundant,
because they are on different branches of the same loop: once a terminal event has
been delivered the shortcut `continue`s *before* the live read, so closing a
finished stream never touches the bus at all; and while a job is still running,
DRA-42's handler funnels a failure into exactly the `live_event = None`
fallthrough a timeout takes, which is the path that notices a terminal status.
Dropping either one reintroduces its own bug: without the shortcut, closing a
finished stream costs a full 15s block; without the handler, a single reset ends
the response with a 500.

**The publish's TTL guard is deleted, not merged.** DRA-42 wrapped the `EXPIRE`
that followed `XADD` in its own `try/except`, because a reset on the second
command aborted a publish whose event was already in the stream. With the two
folded into one `EVAL` there is no second command and no "between", so the guard
covers an unreachable branch. DRA-42's design marked it delete-on-rebase for this
reason, and it is deleted here. The requirement it satisfied is not dropped — it
is restated in the spec delta as an atomicity requirement, which is a stronger
form of the same guarantee. What is *not* touched is DRA-42's other rule, that a
failing append still raises: the bus reports truthfully whether the event reached
the stream, and `BestEffortLiveEventBus` one layer out decides what that means.

**The new publishes return `LiveJobEvent | None`, and nothing reads them.**
DRA-42 retyped `LiveEventBus.publish` and wraps every bus the running service
hands out, so the four cancellation publishes and the four `tool_call` /
`tool_result` publishes this change adds can now return `None` instead of
raising. That is the intended behaviour — the durable row is written first in all
eight cases — but it makes any test that asserted on a publish's *return value*
pass vacuously. Every capture site was checked: the three in this change's tests
build a bare `InMemoryLiveEventBus` or `ValkeyLiveEventBus` with no wrapper, and
every assertion about a publish landing is made on the delivered copy — the SSE
frame, the subscriber's `get`, or the in-memory replay buffer — never on what
`publish` returned. Nothing goes vacuous, and the latency tests that would catch a
dropped publish still fail rather than slow.

**Incidentally, this change is what makes DRA-42's own degraded-latency
requirement true.** DRA-42 requires that a degraded stream's retry delay be
"capped below the interval a healthy stream blocks for so that degrading never
increases latency", and set that cap at 5s. On the code it shipped against, a
healthy stream blocked for `worker_poll_interval_seconds` — 0.2s — so degrading
made the stream up to 25× *slower* than healthy, and the requirement did not hold.
With the idle block at 15s the 0.5–5s degraded range sits where DRA-42 said it
did. No constant changes; the statement simply becomes accurate.

### Known residual: a publish that fails while subscriber reads succeed

With both changes in, the two cases that matter are fast. A successful terminal
publish reaches an open stream in **72 ms**, measured. A Valkey outage bad enough
to break the stream's own reads trips DRA-42's degradation, which polls the
database every **0.5–5s** — so the terminal row arrives inside that, and the
stream still closes.

The gap is between them: a publish fails while the same stream's `XREAD` keeps
succeeding. Nothing has failed *for the stream*, so it is not degraded and it is
sitting in the full 15s block; the terminal event it would have received live is
now waiting on the next durable pass. Worst case is one idle interval — 15
seconds of a cancel that looks hung, exactly the symptom the four new publishes
exist to prevent, in the one case they cannot.

It is accepted, for three reasons. It is narrow: both sides speak to the same
Valkey through the same per-command RESP client, so almost every real fault hits
the reader as well as the writer and lands in the degraded path instead. It is
bounded: one interval, on the terminal event only, and the durable row is written
before the publish in every one of these paths, so nothing is lost — only late. And
the alternatives are each worse than the case they fix:

- *Rejected: shorten the idle interval to cover it.* This is the 2s compromise
  already rejected above, arriving by a different route. It gives back most of a
  measured 75× reduction, permanently and for every stream, to bound a failure
  that requires the publish path to break while the read path does not.
- *Rejected: have a failed publish signal the stream to degrade.* The publisher is
  in the worker process and the stream is in the API process, so the signal has to
  cross processes — through Valkey, which is the thing that just failed, and as
  shared state of exactly the kind the repository forbids.
- *Rejected: shorten the block only while a job is close to terminal.* Needs the
  loop to predict termination, which is the state-derived interval rejected under
  the first decision, and it would still be wrong for the cancel case, where the
  job goes terminal with no warning at all.

What would actually close it is upstream of both changes: connection reuse in
`resp.py`. The per-command connect is the most plausible source of a reset
localised to one publish in the first place, and removing it removes the
asymmetry rather than papering over it. That work is filed separately — see
below. Anyone tuning either `JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS` or
`LIVE_BUS_DEGRADED_MAX_SECONDS` should read this section first: the two constants
bracket this residual from opposite sides, and moving one without the other moves
it.

## Handed back for sequencing

Three findings are real, are quantified, and are deliberately not fixed here.

**1. One TCP connection per command, in `resp.py`.** This is the multiplier under
everything above: it is why a command costs a connect, a write, a read and a
teardown rather than a write and a read, and why command count and span count are
the same number. Connection reuse or pipelining would cut both at a stroke, for
all four services at once, and would have made the `EVAL` decision above
unnecessary. It is not done here for two reasons: the file is shared by
agent-orchestrator, history-service and eval-service (and duplicated privately in
game-service's `session_store.py`, which would drift), and the work is already
filed with DRA-35's measurements — 3 connect-and-teardown cycles per idle ingest
poll, one per command, indefinitely. The call-site view to add to it: after this
change, one streamed turn with one viewer still opens ~508 connections, and every
one of them is avoidable.

**2. history-service's ingest loop is the largest producer on this Valkey.** By
the live measurement, 31,784 of 40,442 commands (78.6%) over 4.4 hours. One idle
cycle issues three commands — `XAUTOCLAIM`, `XREADGROUP BLOCK 2000`, then
`XINFO GROUPS` for the lag check — of which only the `XREADGROUP` blocks and does
anything; the other two are pure overhead repeated every ~2 seconds forever. It
also defeats that service's own deliberate one-span-per-batch design, since three
`valkey.execute` children reappear inside each `history.ingest_batch` span. The
obvious shape of a fix is to reclaim and check lag on a much longer cadence than
the read. It is not done here because it is a different service, because the
reclaim cadence is entangled with at-least-once delivery guarantees for the
ingest stream, and because it is not the symptom DRA-37 reports. It should be its
own issue, and by volume it is the bigger one.

**3. The dashboard multiplies stream count.** One Play page opens one SSE stream
for the parent job, one per *running* subagent entry, and one more duplicating a
running subagent's stream while its output modal is open — so a 10-subagent
fan-out holds 11-12 concurrent streams from a single browser tab, each paying the
per-stream cost independently. Worse, a subagent entry whose
`subagent_completed`/`failed` event is missing stays `running` and holds its
stream indefinitely; the reconciliation that would demote it runs only on page
load. Separately, the reconnect path re-opens with `after=0` and replays the
entire event history, because the endpoint reads only the `?after=` query
parameter and ignores the SSE `Last-Event-ID` header. This change reduces the cost
of each stream by 75× when idle, which is the larger factor; reducing the number
of streams and honouring `Last-Event-ID` is a dashboard-and-endpoint change with
its own correctness surface.

## Risks

- **The Lua script is now on the critical path of every live event.** A malformed
  script would break streaming outright rather than degrade it. Mitigated by
  executing it against the real Valkey 9.1.1 in the running stack on a throwaway
  key: three publishes, entry ids matching what `publish` returned, `XLEN` 3,
  `TTL` 120, and all three read back in order with intact payloads, then the key
  deleted. Also asserted in unit tests, including that the key is passed as
  `KEYS[1]` and not interpolated.
- **A longer idle interval makes any unpublished durable event late.** This is the
  real risk of the change and the reason for the audit above: it converts a 200ms
  delay into a 15-second one for anything persisted without a publish. The audit
  closed every case that a user waits on; what protects it going forward is a spec
  requirement plus two latency tests, one of which runs with an interval longer
  than its own timeout so it fails rather than merely slows. The residue is
  the `progress` running row, accepted. The remaining exposure on the terminal
  path is a job whose worker died between the status write and the publish, which
  no interval fixes.
- **The drain buffer could mask a stream reset.** It holds entries already read,
  and `_last_id` still advances per entry as they are buffered, so a reconnecting
  reader resumes from the last entry *handed out*, not the last one fetched. A
  test covers exactly that.
- **Nothing here touches the DragnCards WebSocket protocol or upstream Elixir
  behaviour.** The live-event bus is internal to agent-orchestrator; game-service
  has its own separate Valkey and its own private RESP client.
- **DRA-36 adds a Valkey-backed DragnCards token cache**, trading Valkey traffic
  for removed HTTP round trips. Its keys are not waste, and nothing in this change
  touches the Bifrost or token cache paths.
