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

logger = logging.getLogger(__name__)


class EvaluationWorker:
    """Background loop that drains pending targets from Postgres.

    Concurrency is bounded by a global semaphore and per-game semaphores
    (cost controls, design Decision 9). All durable state lives in Postgres;
    the worker holds only transient in-flight bookkeeping for one drain cycle.
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
        self._global_sem = asyncio.Semaphore(settings.eval_global_concurrency)
        self._game_sems: dict[str, asyncio.Semaphore] = {}
        self._wake = asyncio.Event()
        # Transient live-push channel + in-flight task registry (durable state
        # stays in Postgres; these are only for live SSE push and cancellation).
        self._live_bus = live_bus
        self._inflight = inflight

    def _game_sem(self, game_id: str) -> asyncio.Semaphore:
        sem = self._game_sems.get(game_id)
        if sem is None:
            sem = asyncio.Semaphore(self._settings.eval_per_game_concurrency)
            self._game_sems[game_id] = sem
        return sem

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
        """Process one batch of pending targets. Returns how many were handled.

        Targets are claimed atomically (pending -> running) so two replicas
        draining concurrently never both evaluate the same row.
        """
        claimed = await self._repository.claim_pending_targets(limit=64)
        if not claimed:
            return 0

        # Read each game's timeline once per batch (shared across its targets).
        by_game: dict[str, list[EvaluatedTargetRow]] = defaultdict(list)
        for target in claimed:
            by_game[target.game_id].append(target)

        tasks: list[asyncio.Task[None]] = []
        for game_id, targets in by_game.items():
            try:
                events = await self._history.list_all_events(game_id)
            except Exception as exc:  # noqa: BLE001 - skip this game's targets
                logger.warning("Failed to read history for game=%s: %s", game_id, exc)
                for target in targets:
                    await self._repository.mark_skipped(
                        target.id, f"history read failed: {exc}"
                    )
                continue
            for target in targets:
                task = asyncio.create_task(self._process_one(target, events))
                # Register so a cancel request can abort the in-flight judge call
                # for this target by cancelling the owning task.
                if self._inflight is not None:
                    self._inflight.register(target.id, task)
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        return len(claimed)

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

    async def _process_one(
        self, target: EvaluatedTargetRow, events: list[StoredEvent]
    ) -> None:
        # Snapshot the per-target judge config (None -> server defaults).
        config = ResolvedJudgeConfig.from_json(target.judge_config_json)
        async with self._global_sem:
            async with self._game_sem(target.game_id):
                # Signal the running transition (claim already wrote it durably).
                self._publish_status(target.request_id)
                try:
                    await self._evaluator.evaluate_target(
                        target_id=target.id,
                        game_id=target.game_id,
                        target_seq=target.target_seq,
                        scope=target.scope,
                        events=events,
                        player=target.player or None,
                        judge_config=config,
                        on_token=self._make_token_sink(target),
                    )
                except JudgeNotConfiguredError:
                    # Already marked skipped with a clear config error.
                    logger.warning(
                        "Skipping target %s: judge not configured", target.id
                    )
                except asyncio.CancelledError:
                    # Cancelled in-flight: the cancel handler already set the
                    # durable ``cancelled`` status and writes no verdict. Do not
                    # re-mark; just surface the transition and stop.
                    logger.info("Target %s cancelled in-flight", target.id)
                    self._publish_status(target.request_id)
                    raise
                except Exception as exc:  # noqa: BLE001 - isolate failures
                    logger.warning(
                        "Unexpected error evaluating target %s: %s",
                        target.id,
                        exc,
                        exc_info=True,
                    )
                    await self._repository.mark_failed(target.id, str(exc))
                finally:
                    if self._inflight is not None:
                        # Only drop the registry entry if it is still THIS task:
                        # a force re-claim may have registered a fresh task for
                        # the same target_id, which must stay cancellable.
                        self._inflight.unregister(target.id, asyncio.current_task())
                    # Terminal (or token) transition -> wake subscribers to
                    # re-read the snapshot and emit a verdict/status event.
                    self._publish_status(target.request_id)
