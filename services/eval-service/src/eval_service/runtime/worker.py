from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict

from eval_service.config import Settings
from eval_service.integrations.history import HistoryClient
from eval_service.judge.config import ResolvedJudgeConfig
from eval_service.runtime.evaluator import Evaluator, JudgeNotConfiguredError
from eval_service.runtime.inflight import InflightRegistry
from eval_service.runtime.live_events import LiveEventBus
from eval_service.schemas.history import StoredEvent
from eval_service.storage.models import EvaluatedTargetRow
from eval_service.storage.repository import Repository
from eval_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# How long a clean shutdown waits for in-flight evaluations before giving up and
# letting the lease reclaim their claims. Sized to fit inside a typical container
# stop grace period rather than to outlast a slow judge call.
SHUTDOWN_DRAIN_SECONDS = 10.0


class EvaluationWorker:
    """Background loop that drains pending targets from Postgres.

    Multiple targets are evaluated CONCURRENTLY, and the concurrency is bounded by
    the durable claim itself: ``claim_pending_targets`` counts the rows already
    ``running`` and takes only the remaining global / per-game capacity, so the
    worker keeps no semaphore, queue, or per-game dictionary of its own. That is
    what makes the cap hold across a restart and across a second replica — and it
    is required here, because this repo forbids services from keeping state in
    memory.

    ``run_forever`` refills CONTINUOUSLY: it holds the tasks it is awaiting and
    re-claims the moment any one of them finishes, rather than draining a batch
    to completion first. The batch-at-a-time shape it replaced made every freed
    slot wait for the SLOWEST target of its batch; measured against a stub judge
    with scripted latency that cost nothing at uniform latency but roughly half
    the throughput under an LLM-like latency spread.

    ``self._tasks`` is NOT the bound and must never become one — ``AGENTS.md``
    forbids reintroducing a semaphore or a per-game dictionary. Something has to
    hold an ``asyncio.Task`` to await it; that is all this set is. Capacity is
    still computed by ``claim_pending_targets`` from the recorded ``running``
    rows, which is why a second replica that has never seen these tasks is
    bounded identically. The test to apply when reading this: *if this set were
    emptied right now, would the cap still hold?* It would.

    The other transient structures are the live-event bus and the in-flight task
    registry, which exist for SSE push and cancellation, not for bounding work.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        history: HistoryClient,
        evaluator: Evaluator,
        poll_interval_seconds: float = 1.0,
        live_bus: LiveEventBus | None = None,
        inflight: InflightRegistry | None = None,
    ):
        self._settings = settings
        self._repository = repository
        self._history = history
        self._evaluator = evaluator
        self._poll_interval = poll_interval_seconds
        self._stop = asyncio.Event()
        self._wake = asyncio.Event()
        # Transient live-push channel + in-flight task registry (durable state
        # stays in Postgres; these are only for live SSE push and cancellation).
        self._live_bus = live_bus
        self._inflight = inflight
        # Lifecycle bookkeeping for continuous refill: the task awaiting each
        # target, keyed by target id so the heartbeat knows which rows this
        # worker still owns. See the class docstring — this is not the bound.
        self._tasks: dict[int, asyncio.Task[bool]] = {}
        # Monotonic timestamp of the last reclaim/heartbeat sweep. A local timer,
        # not claim state: losing it on restart changes nothing but the timing of
        # the next sweep, and every decision it gates is re-read from Postgres.
        self._last_maintenance = 0.0

    def notify(self) -> None:
        """Wake the worker immediately after new targets are enqueued."""
        self._wake.set()

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        # Drain here rather than only in ``run_forever``'s ``finally``: the app
        # lifespan awaits ``stop()`` and then CANCELS the loop task, and a
        # cancelled coroutine cannot wait for anything in its own cleanup. This
        # is the only point at which in-flight evaluations can still be allowed
        # to finish, so their claims are not left to time out.
        await self._drain_inflight_on_stop()

    async def run_forever(self) -> None:
        """Claim, evaluate, and refill freed capacity as soon as it frees.

        One cycle is: sweep stale claims and heartbeat our own, claim into
        whatever capacity the DATABASE says is free, then wait for the first
        in-flight evaluation to finish. Waiting on FIRST_COMPLETED rather than on
        the whole batch is what keeps the slots busy; harvesting every finished
        task per wake is what stops that from turning into one claim (and one
        history read) per target when a burst finishes together.
        """
        logger.info("Evaluation worker started")
        try:
            while not self._stop.is_set():
                try:
                    await self._maintain()
                    started = await self._claim_and_start()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001 - the loop must never die
                    logger.warning("Worker claim cycle failed", exc_info=True)
                    started = 0
                if self._tasks:
                    # Wake on the first completion so its slot is refilled
                    # immediately; the timeout is what paces the heartbeat while
                    # long evaluations are in flight. The stop event is waited on
                    # alongside them, so a shutdown does not sit out a whole
                    # heartbeat interval before the loop notices.
                    stop_waiter = asyncio.ensure_future(self._stop.wait())
                    try:
                        done, _pending = await asyncio.wait(
                            {*self._tasks.values(), stop_waiter},
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=self._heartbeat_interval,
                        )
                    finally:
                        stop_waiter.cancel()
                    # ``stop_waiter`` is not in ``_tasks``, so harvesting it is a
                    # no-op; only finished evaluations free a slot.
                    self._harvest(done)
                elif started == 0:
                    # Nothing running and nothing to claim: idle until woken by a
                    # new request or by the poll interval.
                    try:
                        await asyncio.wait_for(
                            self._wake.wait(), timeout=self._poll_interval
                        )
                    except asyncio.TimeoutError:
                        pass
                    self._wake.clear()
        finally:
            await self._drain_inflight_on_stop()

    @property
    def _heartbeat_interval(self) -> float:
        return self._settings.eval_claim_heartbeat_seconds

    def _harvest(self, done: set[asyncio.Task[bool]]) -> None:
        """Drop finished tasks so their slots can be re-claimed this cycle."""
        for target_id, task in list(self._tasks.items()):
            if task in done:
                del self._tasks[target_id]

    async def _drain_inflight_on_stop(self) -> None:
        """Let outstanding evaluations finish so their claims are not orphaned.

        Bounded deliberately: a container's shutdown grace period is far shorter
        than a slow judge call, so waiting for the judge timeout would just get
        the process killed mid-wait. Anything still running when the bound
        expires is left to the lease — an abandoned claim is recoverable, which
        is exactly what the reclaim sweep is for, so this is an optimisation
        (give back what we can, now) rather than a correctness requirement.
        """
        if not self._tasks:
            return
        tasks = list(self._tasks.values())
        self._tasks.clear()
        try:
            await asyncio.wait(tasks, timeout=SHUTDOWN_DRAIN_SECONDS)
        except Exception:  # noqa: BLE001 - shutdown must not raise
            logger.warning("Waiting for in-flight evaluations failed", exc_info=True)

    async def _maintain(self) -> None:
        """Reclaim stale claims and refresh our own, at the heartbeat cadence.

        Reclaiming is BEST-EFFORT, exactly as history-service's ingest reclaim
        is: DRA-35 established there that letting a failed reclaim abort the
        cycle turns a transient database blip into a hot loop. The same shape
        would fail the same way here, so a failure is logged and the cycle
        continues. ``CancelledError`` is re-raised so shutdown still works.
        """
        now = time.monotonic()
        if now - self._last_maintenance < self._heartbeat_interval:
            return
        self._last_maintenance = now
        # Refresh first: a target this worker is still evaluating must not be
        # visible as stale to its own sweep.
        if self._tasks:
            try:
                await self._repository.heartbeat_targets(tuple(self._tasks))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("Heartbeating in-flight targets failed: %s", exc)
        try:
            result = await self._repository.reclaim_stale_targets(
                lease_seconds=self._settings.eval_claim_lease_seconds,
                max_attempts=self._settings.eval_max_attempts,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Reclaiming stale claims failed (%s: %s); continuing this cycle",
                type(exc).__name__,
                exc,
            )
            return
        if result.reclaimed_ids:
            # A steady trickle of these means a worker is dying repeatedly.
            logger.warning(
                "Reclaimed %d stale evaluation claim(s): %s",
                len(result.reclaimed_ids),
                list(result.reclaimed_ids),
            )
        if result.failed_ids:
            logger.error(
                "Gave up on %d target(s) after repeated abandoned claims: %s",
                len(result.failed_ids),
                list(result.failed_ids),
            )

    async def _claim_and_start(self) -> int:
        """Claim into the free capacity and start a task per claimed target.

        Returns how many tasks were started. The capacity is the database's
        answer, not this worker's: ``claim_pending_targets`` counts the rows
        already ``running`` — including those held by another replica — and
        hands back only what is left.
        """
        claimed = await self._repository.claim_pending_targets(
            limit=64,
            global_limit=self._settings.eval_global_concurrency,
            per_game_limit=self._settings.eval_per_game_concurrency,
        )
        if not claimed:
            return 0
        started = 0
        for game_id, targets in self._group_by_game(claimed).items():
            events = await self._read_events_or_fail(game_id, targets)
            if events is None:
                continue
            for target in targets:
                self._start(target, events)
                started += 1
        return started

    def _start(self, target: EvaluatedTargetRow, events: list[StoredEvent]) -> None:
        task = asyncio.create_task(self._process_one(target, events))
        self._tasks[target.id] = task
        # Register so a cancel request can abort the in-flight judge call for
        # this target by cancelling the owning task.
        if self._inflight is not None:
            self._inflight.register(target.id, task)

    @staticmethod
    def _group_by_game(
        claimed: list[EvaluatedTargetRow],
    ) -> dict[str, list[EvaluatedTargetRow]]:
        """Group a claim so each game's timeline is read once, not once per target."""
        by_game: dict[str, list[EvaluatedTargetRow]] = defaultdict(list)
        for target in claimed:
            by_game[target.game_id].append(target)
        return by_game

    async def _read_events_or_fail(
        self, game_id: str, targets: list[EvaluatedTargetRow]
    ) -> list[StoredEvent] | None:
        """Read a game's timeline, failing its targets if it cannot be read."""
        try:
            return await self._history.list_all_events(game_id)
        except Exception as exc:  # noqa: BLE001 - fail this game's targets
            logger.warning("Failed to read history for game=%s: %s", game_id, exc)
            for target in targets:
                # An unreadable timeline is an error, not a deliberate skip:
                # record it as ``failed`` with the reason so the UI shows it.
                await self._repository.mark_failed(
                    target.id,
                    f"history read failed: {exc}",
                    attempts=target.attempts,
                )
                self._publish_status(target.request_id)
            return None

    async def drain_once(self) -> int:
        """Process one batch of pending targets, concurrently.

        Returns how many targets made PROGRESS — reached a terminal state or wrote
        a verdict — NOT how many rows were touched. A round/game roll-up whose
        children are still in flight is re-deferred to ``pending`` and made no
        progress; reporting those as handled would make ``run_forever`` skip its
        wait and hot-loop on the database while the children run. A cycle where
        everything deferred therefore reports 0 and is treated as idle.

        Targets are claimed atomically (pending -> running) so two replicas
        draining concurrently never both evaluate the same row, and the claim is
        capacity-bounded so the in-flight count respects the configured caps
        without any in-process registry of running work.

        NOTE: this drains ONE batch to completion, which is deliberately not how
        ``run_forever`` schedules work — it refills continuously instead, so a
        freed slot never waits for the slowest member of its batch. This method
        remains as the single-batch entry point the test suites drive, and as the
        unit of work whose per-target semantics both paths share.
        """
        claimed = await self._repository.claim_pending_targets(
            limit=64,
            global_limit=self._settings.eval_global_concurrency,
            per_game_limit=self._settings.eval_per_game_concurrency,
        )
        if not claimed:
            return 0
        # Counts the targets that progressed. A plain int is not shared mutable
        # state across cycles -- it is a local tally for this call.
        progressed = 0

        tasks: list[asyncio.Task[bool]] = []
        # Read each game's timeline once per batch (shared across its targets).
        for game_id, targets in self._group_by_game(claimed).items():
            events = await self._read_events_or_fail(game_id, targets)
            if events is None:
                # A failure is a terminal outcome, so the cycle did progress.
                progressed += len(targets)
                continue
            for target in targets:
                task = asyncio.create_task(self._process_one(target, events))
                # Register so a cancel request can abort the in-flight judge call
                # for this target by cancelling the owning task.
                if self._inflight is not None:
                    self._inflight.register(target.id, task)
                tasks.append(task)

        if tasks:
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
            # A cancelled task surfaces as an exception here; cancellation is a
            # terminal transition, so it counts as progress just like a verdict.
            progressed += sum(1 for outcome in outcomes if outcome is not False)
        return progressed

    def _publish_status(self, request_id: str) -> None:
        if self._live_bus is not None:
            # Wake live subscribers; they re-read the authoritative snapshot
            # from Postgres, so we only need to signal "something changed".
            self._live_bus.publish(request_id, "status", {"request_id": request_id})

    def _make_token_sink(self, target: EvaluatedTargetRow):
        bus = self._live_bus
        if bus is None:
            return None

        async def sink(delta: str) -> None:
            # Skip the per-token publish work entirely when nobody is watching
            # this request (the common background-evaluation case).
            if bus.has_subscribers(target.request_id):
                bus.publish(
                    target.request_id,
                    "token",
                    {
                        "target_seq": target.target_seq,
                        "scope": target.scope,
                        "delta": delta,
                    },
                )

        return sink

    def _make_error_sink(self, target: EvaluatedTargetRow):
        """Wake live subscribers when a mid-evaluation failure is recorded.

        The detail itself is already durable on the target row, so — exactly like
        a status transition — this only signals "something changed" and the stream
        re-reads the authoritative snapshot from Postgres. Unlike the token sink
        this fires even with nobody watching (it is rare, and a client connecting
        later must still find the error in the snapshot, which it does).
        """
        if self._live_bus is None:
            return None

        async def sink(_detail: str) -> None:
            self._publish_status(target.request_id)

        return sink

    async def _process_one(
        self, target: EvaluatedTargetRow, events: list[StoredEvent]
    ) -> bool:
        """Evaluate one claimed target. Returns whether it made progress.

        False means the target was re-deferred to ``pending`` because the children
        it depends on are still being graded; see :meth:`drain_once` for why that
        distinction matters. Concurrency is NOT gated here — the capacity-bounded
        claim in :meth:`drain_once` already limits how many of these run at once,
        so there is no semaphore to acquire and no per-game structure to keep.
        """
        # Snapshot the per-target judge config (None -> server defaults).
        config = ResolvedJudgeConfig.from_json(target.judge_config_json)
        # One span per graded target: the judge lifecycle is the repo-specific
        # workflow generic instrumentation cannot explain, and it is where the
        # latency lives. Identifiers, scope and outcome ONLY — never the
        # assembled prompt, the recorded events, or the judge's response.
        with tracer.start_as_current_span(
            "eval.evaluate_target",
            attributes={
                "eval.target_id": target.id,
                "eval.request_id": target.request_id,
                "eval.scope": target.scope,
                "eval.target_seq": target.target_seq,
                "eval.events_considered": len(events),
                "game.id": target.game_id,
            },
        ) as target_span:
            # Signal the running transition (claim already wrote it durably).
            self._publish_status(target.request_id)
            try:
                evaluated = await self._evaluator.evaluate_target(
                    target_id=target.id,
                    game_id=target.game_id,
                    target_seq=target.target_seq,
                    scope=target.scope,
                    events=events,
                    player=target.player or None,
                    judge_config=config,
                    # The epoch this target was claimed at. Every terminal write
                    # is conditional on it, so if the claim was revoked mid-flight
                    # — by a force re-evaluation, a cancel, or a stale-claim
                    # reclaim — this evaluation's verdict is discarded instead of
                    # overwriting the row of the worker that now owns it.
                    attempts=target.attempts,
                    on_token=self._make_token_sink(target),
                    on_error=self._make_error_sink(target),
                )
                target_span.set_attribute("eval.outcome", "evaluated")
                return evaluated
            except JudgeNotConfiguredError:
                # Already marked failed with a clear config error.
                target_span.set_attribute("eval.outcome", "not_configured")
                logger.warning("Target %s failed: judge not configured", target.id)
                return True
            except asyncio.CancelledError:
                # Cancelled in-flight: the cancel handler already set the durable
                # ``cancelled`` status and writes no verdict. Do not re-mark; just
                # surface the transition and stop.
                target_span.set_attribute("eval.outcome", "cancelled")
                logger.info("Target %s cancelled in-flight", target.id)
                self._publish_status(target.request_id)
                raise
            except Exception as exc:  # noqa: BLE001 - isolate failures
                # The exception text can embed a gateway body; record it durably
                # (sanitized at the repository boundary) but keep only the
                # outcome on the span.
                target_span.set_attribute("eval.outcome", "failed")
                logger.warning(
                    "Unexpected error evaluating target %s: %s",
                    target.id,
                    exc,
                    exc_info=True,
                )
                await self._repository.mark_failed(
                    target.id, str(exc), attempts=target.attempts
                )
                return True
            finally:
                if self._inflight is not None:
                    # Only drop the registry entry if it is still THIS task: a
                    # force re-claim may have registered a fresh task for the
                    # same target_id, which must stay cancellable.
                    self._inflight.unregister(target.id, asyncio.current_task())
                # Terminal (or token) transition -> wake subscribers to re-read
                # the snapshot and emit a verdict/status event.
                self._publish_status(target.request_id)
