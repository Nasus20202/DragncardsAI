## Why

DRA-42 reports that orchestrator mode "fails consequently with connection problems",
and the owner confirms it plainly: orchestrator mode does not work. Every fatal
traceback in the report bottoms out in the same place — a
`ConnectionResetError: [Errno 104] Connection reset by peer` raised from one Valkey
command inside the shared RESP client. Unguarded call sites turned that one transient
error into several distinct user-visible failures. Three appear in the report's
tracebacks; a fourth was found by auditing the remaining call sites, and it is the one
most specific to orchestrator mode.

**1. The SSE stream endpoint died.** `job_event_stream.py` awaited
`live_subscriber.get(...)` with nothing around it. A reset there propagated out of
the async generator, through Starlette's `stream_response`, and killed the streaming
response, so the Next.js proxy reported `failed to pipe response` /
`TypeError: terminated` / `SocketError: other side closed` and returned
`GET /api/proxy/orchestrator/jobs/.../events/stream 500` — once after 41 s and once
after 52 s. In the browser this is the live transcript simply stopping mid-run.

**2. A reset during a streaming delta killed the whole model call.**
`on_bifrost_delta` publishes each accumulated chunk, the publish sits inside the
callback that `_stream_chat_completion` awaits, and that sits inside the job's own
`try`. So a single failed publish aborted the model call and then marked an
otherwise healthy job failed. This is not confined to deltas: roughly twenty
publishes across the job runtime — tool calls, questions, skills, subagent
lifecycle, terminal events — all sit inside the same `try`, and *any* of them could
end the job.

**3. Failure recording itself threw.** `record_failure` did
`append_event` → `publish` → `mark_job_failed` with no guard, so a failed publish
skipped `mark_job_failed` and escaped into `worker._run_job`, which fell back to
`_force_terminal_failure`. That guard works — the job did reach `"failed"` — but it
got there by the crash path, so the recorded cause became `worker_crash` instead of
the real error and the job's event list carried the `failure` event twice. The
report's `"Failed to announce the crash of job ..."` line is that fallback's own
publish failing in turn.

**4. A parent waiting on a subagent was killed by its child's event stream.** Not in
the report's tracebacks, and found by auditing the remaining subscriber reads.
`resolve_child_outcome` consumes the child's live events so `wait_for_subagent` can
return the moment the child finishes, and that read was unguarded. A reset escaped the
wait, escaped the tool dispatch, and reached the parent job's own handler — so a blip
on a *child's* stream failed the *parent*. This is precisely the orchestrated
multi-agent path the issue is titled after, and it is arguably the site that made
"orchestrator mode" the thing that fails. The child's persisted row was already the
authority for this wait, so a correct fallback was sitting right there unused.

**The principle being applied.** The durable `job_events` row in Postgres is the
source of truth; the live bus is a latency optimisation. Every publish in the job
runtime is preceded by an `append_event`, and the SSE stream polls `list_events` as
well as forwarding the bus. So when a publish fails the event is not lost, it is
*late* — and a correct degraded behaviour exists on every one of these paths.

## What Changes

- A new `BestEffortLiveEventBus` decorator makes `publish` unable to fail its
  caller: it logs and returns `None`. `LiveEventBus.publish` is typed
  `LiveJobEvent | None` accordingly. It is applied in `create_app`, where every
  consumer in the running service reads its bus from `app.state`, and again in
  `WorkerService.__init__` so the guarantee holds however the job runtime is wired.
  The wrap is idempotent, and `unwrap_live_event_bus` recovers the concrete bus for
  the readiness probe, which asks which bus is configured rather than whether it is
  wrapped.
- A subagent wait degrades to polling the child's row. A failing live read no longer
  escapes `resolve_child_outcome`; the wait loses its early return and nothing else,
  and its absolute deadline is unchanged.
- The SSE stream degrades to poll-only instead of dying. A failing
  `live_subscriber.get` is routed into the same path a subscriber timeout takes, so
  a job that finishes while the bus is down still closes its stream instead of
  hanging on it. A new `LiveBusDegradation` object — created inside `stream()` and
  discarded with it — paces the retry: short, doubling per consecutive failure,
  capped, and reset by the first success.
- `ValkeyLiveEventBus.publish` no longer fails on the `EXPIRE` that follows a
  successful `XADD`. The event is already in the stream at that point and a TTL
  refresh is housekeeping the next publish redoes.
- Logging follows DRA-35's discipline, adapted for a call rate DRA-35 did not have.
  A publish happens once per streaming delta, so a `FailureStreak` helper emits one
  traceback for the first failure of a streak, counted warnings only at powers of
  two after it, and one recovery line naming the streak length. Twenty thousand
  failed publishes cost about fifteen log lines.

**Which failures are now tolerated, and which still surface.** Tolerated: a live
`publish` failing anywhere, and the TTL refresh that follows a successful `XADD`.
Both are safe for the same reason — the durable row was already written and the
stream's own poll delivers it. Still surfacing exactly as before: every Postgres
write, `append_event` included; a failing `XADD` inside `ValkeyLiveEventBus`, which
still raises to its caller; `mark_job_failed` / `mark_job_completed` /
`mark_job_interrupted`; and `asyncio.CancelledError`, which is `BaseException` and is
deliberately never caught, so shutdown still cancels in-flight jobs. The one event
with no durable twin is `compaction`, whose summary lives on its own compaction job;
dropping its live copy means the running transcript shows the summary only after a
reload, which is far cheaper than failing the job that was mid-compaction.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `agent-orchestrator`: publishing to the live job-event bus becomes best-effort
  against the durable event row; the job event stream degrades to durable-poll-only
  on a live-bus failure rather than terminating the response; a subagent wait degrades
  to its existing row poll rather than failing the parent job; and a live-bus failure
  alone no longer diverts a prompt run into the `worker_crash` fallback.

## Impact

- `services/agent-orchestrator/src/agent_orchestrator/runtime/live_event_resilience.py` — new: `BestEffortLiveEventBus`, `LiveBusDegradation`, `FailureStreak`
- `services/agent-orchestrator/src/agent_orchestrator/runtime/live_events.py` — `publish` returns `LiveJobEvent | None`; the TTL refresh is best-effort
- `services/agent-orchestrator/src/agent_orchestrator/runtime/job_event_stream.py` — a live-bus failure degrades the stream instead of ending it
- `services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py` — a subagent wait tolerates a failing live read
- `services/agent-orchestrator/src/agent_orchestrator/runtime/worker.py` — the job runtime wraps its bus
- `services/agent-orchestrator/src/agent_orchestrator/runtime/app.py` — the service-wide bus is wrapped once
- `services/agent-orchestrator/src/agent_orchestrator/api/routers/meta.py` — readiness unwraps before its identity check
- `services/agent-orchestrator/tests/unit/test_live_event_resilience.py` — new: thirteen regression pins, eight of which fail on the base
- `services/agent-orchestrator/tests/integration/{conftest.py,api_test_support.py,test_api_jobs.py}` — an HTTP-level pin that the SSE endpoint answers 200 with the bus down
- `services/agent-orchestrator/README.md` — documents the degraded behaviour and its logging

## Deliberately Not Done

- **Connection pooling.** The shared RESP client still opens and closes one TCP
  connection per command; the archived `dra-35-connection-errors` change measured 3
  connect+teardown cycles per idle ingest poll. That churn is why a mid-command reset
  is plausible at all, and pooling remains the right cure for the resets themselves.
  It is not built here: `resp.py` is shared by four services, DRA-37 is concurrently
  reducing Valkey call volume in the same area, and this change is urgent. The
  resilience here is correct and necessary whether or not pooling later lands —
  pooling would make resets rarer, not impossible, and a rare reset would still have
  killed a job without these guards.
- **Root-causing the resets.** Established as environmental by DRA-35 and not
  revisited: the in-Docker stack ran an hour clean over the compose network, while
  the reporter runs the services outside Docker against host-published ports.
- **Reordering the terminal transitions.** `append_event` still precedes every
  `publish`, and `mark_job_*` still follows it, exactly as before. Reordering was
  considered and rejected — see `design.md`.
- **Re-subscribing on failure.** Retrying the existing subscriber is the whole of the
  recovery available, and replacing it would be strictly worse. See `design.md`.
