"""Degraded-mode behaviour for the live job-event bus.

The live bus is a latency optimisation, not a system of record. Every event the
job runtime publishes has already been written to ``job_events`` in Postgres by
the time it is published, and the SSE stream polls that table as well as
forwarding the bus. So when Valkey is transiently unreachable the correct
outcome is *later*, never *never*: the durable row is still there and the
stream's own poll delivers it.

DRA-42 is what happens without that reasoning applied. A
``ConnectionResetError`` from a single Valkey command killed a streaming model
call mid-response, aborted a job's own failure handling, and terminated the SSE
response so the browser saw a 500 and the transcript simply stopped. This module
holds the two pieces that stop that:

* :class:`BestEffortLiveEventBus` — a decorator that makes ``publish`` unable to
  fail its caller.
* :class:`LiveBusDegradation` — the per-stream backoff a reader uses when its
  subscriber keeps failing, so the stream falls back to the durable poll instead
  of dying.

Both follow DRA-35's logging discipline: one traceback per outage, a thinning
trail of counted warnings after it, and a recovery line when it ends. A publish
happens once per streaming delta, so "one warning per failure" would be a flood
in its own right — see :class:`FailureStreak`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_orchestrator.runtime.live_events import (
    LiveEventBus,
    LiveEventSubscriber,
    LiveJobEvent,
)

logger = logging.getLogger(__name__)

#: How long a stream waits before retrying a live subscriber that just failed.
#: While the bus is down the durable poll is the stream's *only* source, so this
#: doubles as the transcript's latency. It is deliberately far shorter than the
#: healthy idle block: degrading must not make the stream feel slower than it
#: does when everything works.
LIVE_BUS_DEGRADED_MIN_SECONDS = 0.5

#: Ceiling for that retry delay. Bounds the command volume a long outage costs
#: per open stream while keeping worst-case latency well inside the healthy idle
#: block.
LIVE_BUS_DEGRADED_MAX_SECONDS = 5.0


class FailureStreak:
    """Counts consecutive failures and decides which of them are worth logging.

    A failing Valkey command is cheap to retry and can therefore repeat at the
    rate of whatever is retrying it — once per streaming delta for a publish,
    once per backoff tick for a stream. Logging each one turns a recoverable
    outage into an unreadable log, which is the mistake DRA-35 fixed in the
    ingest loop and which this class exists to avoid repeating.

    The rule: the first failure of a streak carries a full traceback, because
    that is the one that contains the diagnosis. After that, warnings are
    emitted only when the count reaches a power of two, so a streak of ten
    thousand costs about fourteen lines rather than ten thousand. The end of a
    streak is always reported, with its length, so a log reader can see both
    that it happened and that it stopped.
    """

    def __init__(self, *, log: logging.Logger | None = None):
        self._log = log or logger
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def failing(self) -> bool:
        return self._count > 0

    def note_failure(self, message: str, *args: Any) -> int:
        """Record one failure, log it if the discipline says so, return the streak length."""
        self._count += 1
        if self._count == 1:
            self._log.exception(message, *args)
        elif self._count & (self._count - 1) == 0:  # power of two
            self._log.warning(
                "%s (%d consecutive)",
                message % args if args else message,
                self._count,
            )
        return self._count

    def note_success(self, message: str, *args: Any) -> None:
        """Record a success, logging a recovery line when it ends a streak."""
        if self._count == 0:
            return
        self._log.info(
            "%s after %d consecutive failure(s)",
            message % args if args else message,
            self._count,
        )
        self._count = 0


class BestEffortLiveEventBus:
    """A :class:`LiveEventBus` whose ``publish`` cannot fail its caller.

    Wrapping is what makes the tolerance structural rather than a habit every
    call site has to remember. There are roughly twenty publishes across the job
    runtime — deltas, tool calls, questions, skills, terminal events — and on the
    unwrapped bus *any* of them could end the job, because they all run inside
    the ``try`` block whose handler marks the job failed. A single reset during
    one streaming delta was enough to fail an otherwise healthy run (DRA-42).

    Swallowing is safe here for one specific reason, and only for that reason:
    the caller has already written the event to ``job_events``, and the SSE
    stream polls that table. A dropped publish therefore costs the browser the
    difference between "immediately" and "on the next poll" — nothing more. The
    one event with no durable twin is ``compaction``, whose summary lives on its
    own compaction job rather than in the compacted job's event list; losing its
    live copy means the running transcript does not show the summary until the
    session is reloaded, which is a far smaller price than failing the job that
    was mid-compaction.

    ``publish`` returns ``None`` when the event did not reach the bus. No caller
    in this service reads the return value, and the type says plainly that a
    publish is not a guarantee.
    """

    def __init__(self, inner: LiveEventBus, *, log: logging.Logger | None = None):
        self._inner = inner
        self._streak = FailureStreak(log=log)

    @property
    def inner(self) -> LiveEventBus:
        """The wrapped bus, for callers that need its concrete identity."""
        return self._inner

    async def publish(
        self,
        job_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        *,
        durable_event_id: int | str | None = None,
    ) -> LiveJobEvent | None:
        try:
            event = await self._inner.publish(
                job_id,
                event_type,
                payload_json,
                durable_event_id=durable_event_id,
            )
        except Exception:
            # `CancelledError` derives from BaseException and is deliberately not
            # caught: a cancelled job must still cancel.
            self._streak.note_failure(
                "Live publish of %s for job %s failed; the durable row stands and "
                "the event stream's poll will deliver it",
                event_type,
                job_id,
            )
            return None
        self._streak.note_success("Live publishing recovered for job %s", job_id)
        return event

    async def subscribe(self, job_id: str) -> LiveEventSubscriber:
        return await self._inner.subscribe(job_id)

    async def aclose(self) -> None:
        await self._inner.aclose()


def best_effort_live_event_bus(bus: LiveEventBus) -> LiveEventBus:
    """Wrap ``bus`` so publishing is best-effort, idempotently.

    The wrap is applied both where the app builds its bus and inside
    ``WorkerService``, so the job runtime is tolerant however it was wired —
    including in tests, which construct it directly. Being idempotent is what
    lets both do it without double-counting a failure streak.
    """
    if isinstance(bus, BestEffortLiveEventBus):
        return bus
    return BestEffortLiveEventBus(bus)


def unwrap_live_event_bus(bus: LiveEventBus) -> LiveEventBus:
    """Return the concrete bus behind any best-effort wrapper."""
    while isinstance(bus, BestEffortLiveEventBus):
        bus = bus.inner
    return bus


class LiveBusDegradation:
    """Per-stream backoff for a live subscriber that keeps failing.

    An SSE stream has two sources for the same events: it polls ``list_events``
    in Postgres and it forwards the live bus. When the bus fails the stream must
    keep going on the poll alone, and the interesting question is how often to
    poll while degraded — because the poll has stopped being a backstop and
    become the only source.

    Both obvious answers are wrong. Keeping the healthy idle block would make the
    transcript lag by that whole interval, since the block exists precisely
    *because* the live bus normally delivers first. Retrying immediately would
    spin: a failing command fails fast, so there is no blocking read left to pace
    the loop. So the delay starts short enough that the transcript still reads as
    live, doubles per consecutive failure to bound what a long outage costs, and
    is capped well below the healthy idle block. The first successful read clears
    it and the stream returns to the long block, which is what keeps a healthy
    idle stream cheap.

    Retrying is all the recovery there is to do, and it is enough. The shared
    RESP client opens a fresh TCP connection per command, so a subscriber holds
    no socket to rebuild and a failed read leaves its stream cursor untouched —
    the next attempt resumes exactly where it left off. Replacing the subscriber
    would be strictly worse: a new one starts from ``0-0`` and replays the whole
    retained stream, re-delivering hundreds of entries the client already has.

    One instance belongs to one ``stream()`` call and dies with it. There is no
    shared registry: nothing here is state the service would want back.
    """

    def __init__(
        self,
        job_id: str,
        *,
        min_seconds: float | None = None,
        max_seconds: float | None = None,
        log: logging.Logger | None = None,
    ):
        self._job_id = job_id
        self._min_seconds = (
            LIVE_BUS_DEGRADED_MIN_SECONDS if min_seconds is None else min_seconds
        )
        self._max_seconds = (
            LIVE_BUS_DEGRADED_MAX_SECONDS if max_seconds is None else max_seconds
        )
        self._delay = self._min_seconds
        self._streak = FailureStreak(log=log)

    @property
    def degraded(self) -> bool:
        return self._streak.failing

    @property
    def delay_seconds(self) -> float:
        return self._delay

    async def note_failure(self) -> None:
        """Log the failure per the streak discipline and wait before retrying.

        Called from inside an ``except`` block, so ``logger.exception`` still has
        the live exception to render.
        """
        delay = self._delay
        self._streak.note_failure(
            "Live event subscription for job %s failed; serving durable events "
            "only and retrying in %.1fs",
            self._job_id,
            delay,
        )
        self._delay = min(self._delay * 2, self._max_seconds)
        await asyncio.sleep(delay)

    def note_success(self) -> None:
        self._streak.note_success(
            "Live event subscription for job %s recovered", self._job_id
        )
        self._delay = self._min_seconds
