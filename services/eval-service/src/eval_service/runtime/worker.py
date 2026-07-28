from __future__ import annotations

import asyncio
import logging
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


class EvaluationWorker:
    """Background loop that drains pending targets from Postgres.

    Multiple targets are evaluated CONCURRENTLY, and the concurrency is bounded by
    the durable claim itself: ``claim_pending_targets`` counts the rows already
    ``running`` and takes only the remaining global / per-game capacity, so the
    worker keeps no semaphore, queue, or per-game dictionary of its own. That is
    what makes the cap hold across a restart and across a second replica — and it
    is required here, because this repo forbids services from keeping state in
    memory. The only transient structures left are the live-event bus and the
    in-flight task registry, which exist for SSE push and cancellation, not for
    bounding work.
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

    def notify(self) -> None:
        """Wake the worker immediately after new targets are enqueued."""
        self._wake.set()

    async def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    async def run_forever(self) -> None:
        logger.info("Evaluation worker started")
        while not self._stop.is_set():
            try:
                processed = await self.drain_once()
            except Exception:  # noqa: BLE001 - the loop must never die
                logger.warning("Worker drain cycle failed", exc_info=True)
                processed = 0
            if processed == 0:
                try:
                    await asyncio.wait_for(
                        self._wake.wait(), timeout=self._poll_interval
                    )
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()

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

        # Read each game's timeline once per batch (shared across its targets).
        by_game: dict[str, list[EvaluatedTargetRow]] = defaultdict(list)
        for target in claimed:
            by_game[target.game_id].append(target)

        tasks: list[asyncio.Task[bool]] = []
        for game_id, targets in by_game.items():
            try:
                events = await self._history.list_all_events(game_id)
            except Exception as exc:  # noqa: BLE001 - fail this game's targets
                logger.warning("Failed to read history for game=%s: %s", game_id, exc)
                for target in targets:
                    # An unreadable timeline is an error, not a deliberate skip:
                    # record it as ``failed`` with the reason so the UI shows it.
                    await self._repository.mark_failed(
                        target.id, f"history read failed: {exc}"
                    )
                    self._publish_status(target.request_id)
                    # A failure is a terminal outcome, so the cycle did progress.
                    progressed += 1
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
                await self._repository.mark_failed(target.id, str(exc))
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
