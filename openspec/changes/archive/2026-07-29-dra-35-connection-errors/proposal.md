## Why

DRA-35 reports a flood of `ConnectionResetError: [Errno 104] Connection reset by peer`
from two call sites, both bottoming out in the shared RESP client at
`services/shared/src/dragncards_common/resp.py` line 145, on the
`await writer.wait_closed()` inside the `finally` block. That line is wrapped in
`try: ... except Exception: pass`, which made the report look impossible and sent
three separate rounds of analysis after checkouts, stale bytecode and shadowed
modules. All of those were wrong. The behaviour reproduces on the current code.

**What is actually happening.** asyncio stores *one* exception instance on the
transport's protocol and hands that same object to both the `StreamReader` and the
connection's close waiter. When a connection dies mid-command:

1. `_read_resp` raises that instance from `readexactly`. This is a genuine failure —
   the command did not complete — and `except BaseException as exc: ... raise`
   deliberately re-raises it. An error here is correct and by design.
2. Unwinding enters the `finally`, which calls `await writer.wait_closed()`. The
   close waiter holds *the same exception object*, so it is raised a second time.
3. `except Exception: pass` catches and discards that second raise. The guard works.
4. But raising it had already appended the `wait_closed` frames to the object's
   `__traceback__`, and tracebacks are cumulative on the object.
5. The original exception finishes propagating out of `execute()` carrying a
   traceback whose final frames are `resp.py:145` → `streams.py:358`.

So the guard never failed, and nothing about the reporter's environment was unusual.
A mid-command read failure was simply *reporting itself at the cleanup line*, which
is why every reader of the traceback went looking at the wrong place. This was
confirmed by exception identity: the object raised inside `_read_resp` and the object
escaping `execute()` are the same `id()`.

**Why it became a flood.** Two amplifiers, both older than the report:

- `process_batch` calls `reclaim_pending()` as its first statement, unguarded. One
  failed `XAUTOCLAIM` therefore aborted the entire batch before `XREADGROUP` ever
  ran, so nothing was ingested at all.
- `run_forever` retried on a fixed 500 ms delay and called `logger.exception` every
  time, so a persistent fault emitted a full stack roughly twice a second forever.
  Because the failure path skips the 2 s blocking read, the broken loop spins about
  four times faster than the healthy one.

Measured: 60 s of continuous failure produced ~1440 log lines.

**What this change does not claim.** The root cause of the resets themselves is not
established and is very likely environmental rather than a code defect. The owner's
Docker stack, reaching Valkey over the compose network, ran for over an hour with
zero occurrences; the reporter runs the services outside Docker against
host-published Valkey ports. `6a4972e` (DRA-23 observability) was investigated as the
regression boundary and refuted: its diff only wraps `process_batch` in a span, and
the unguarded `reclaim_pending()` call, the `logger.exception` and the 500 ms sleep
are all byte-identical before it. The amplification is a real defect on any
environment and is fixed here regardless.

## What Changes

- `resp.py` sets `skip_wait_closed = True` on the error path, so a failed command no
  longer awaits a close waiter that holds the exception already propagating. The
  traceback then names the call that actually failed. `writer.close()` still runs, so
  the socket is still released; only the *await* is skipped, and only when the command
  has already failed. The success path is unchanged and still guarded, because a reset
  can legitimately arrive after a complete reply.
- `process_batch` tolerates a failing `reclaim_pending()`: it logs one warning line
  and proceeds to read the batch. Reclaiming is a best-effort recovery pass, so the
  entries it would have claimed stay pending and are picked up by a later cycle —
  which is exactly what `XAUTOCLAIM`'s idle window exists for.
- `run_forever` retries with exponential backoff from 0.5 s to a 30 s ceiling, logs
  one traceback for the first failure of a streak, then one counted warning per retry,
  and logs a recovery line when the streak ends.
- `BifrostClient` cache warnings drop `exc_info=True`. The degradation itself was
  already correct and is unchanged.

**Which failures are now tolerated, and which still surface.** Only the reclaim pass
is newly tolerated, and it loses nothing: a stale pending entry that is not claimed
this cycle remains in the Pending Entries List and is claimed later. Every failure
that can lose an event still surfaces — a failing `XREADGROUP`, a failing commit, a
failing `XACK` and a malformed envelope all behave exactly as before, and a batch that
cannot be read still raises, logs and retries. No event is dropped or acked without a
successful commit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `history-event-store`: ingest batch isolation for the reclaim pass, and bounded
  retry pacing with de-duplicated logging for a repeatedly failing poll loop.
- `agent-orchestrator`: model-cache transport failures log one line instead of a stack
  trace; the fall-through to a live fetch is unchanged.
- `infrastructure`: the shared RESP client attributes a failed command to the call
  that failed rather than to its own cleanup path.

## Impact

- `services/shared/src/dragncards_common/resp.py` — skip the close waiter on the error path
- `services/shared/tests/test_resp.py` — socket-level RST tests for both paths
- `services/history-service/src/history_service/runtime/ingest.py` — reclaim isolation, backoff, log de-duplication
- `services/history-service/tests/unit/test_ingest.py` — regression pins for both
- `services/history-service/tests/unit/test_telemetry.py` — permit the `history.reclaim_failed` span flag
- `services/agent-orchestrator/src/agent_orchestrator/integrations/bifrost.py` — drop tracebacks from recoverable cache warnings

## Deliberately Not Done

- **Connection pooling.** The client opens and closes one TCP connection per command;
  measured at 3 connect+teardown cycles per idle ingest poll, sustained forever. That
  churn is the reason a mid-command reset is plausible rather than exotic, and DRA-36
  is adding a further Valkey path. Pooling is the right long-term fix, but it changes
  shared code that four services depend on, and DRA-35 is urgent. Filed separately
  with these measurements rather than built under time pressure.
- **Root-causing the resets.** Not reproducible on the in-Docker stack; needs the
  reporter's host-networking setup to investigate, which is not reachable from here.
