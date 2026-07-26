from __future__ import annotations

import logging
from datetime import datetime, timezone

from history_service.config import Settings
from history_service.integrations.game_service import GameServiceClient
from history_service.schemas.envelope import StoredSnapshot
from history_service.storage.repository import Repository

logger = logging.getLogger(__name__)


class SnapshotService:
    """Evaluates the snapshot cadence policy after commits and stores snapshots.

    Cadence is count- AND time-based: a snapshot is due when either
    ``SNAPSHOT_EVERY_N_EVENTS`` events have been committed since the last
    snapshot, or ``SNAPSHOT_MAX_INTERVAL_SECONDS`` has elapsed since the last
    snapshot while new events exist.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        game_service: GameServiceClient,
    ):
        self._settings = settings
        self._repository = repository
        self._game_service = game_service

    async def is_snapshot_due(self, game_id: str, current_seq: int) -> bool:
        snapshots = await self._repository.list_snapshots(game_id)
        if not snapshots:
            # First snapshot is due once enough events accrue.
            return current_seq >= self._settings.snapshot_every_n_events
        latest = snapshots[-1]
        events_since = current_seq - latest.snapshot_at_seq
        if events_since <= 0:
            return False
        if events_since >= self._settings.snapshot_every_n_events:
            return True
        elapsed = (_utc_now() - _as_utc(latest.created_at)).total_seconds()
        return elapsed >= self._settings.snapshot_max_interval_seconds

    async def maybe_snapshot(
        self, game_id: str, current_seq: int
    ) -> StoredSnapshot | None:
        """Take and store a snapshot if cadence policy says one is due."""
        if not await self.is_snapshot_due(game_id, current_seq):
            return None
        return await self.take_snapshot(game_id, current_seq)

    async def maybe_snapshot_best_effort(
        self, game_id: str, current_seq: int
    ) -> StoredSnapshot | None:
        """Best-effort wrapper around :meth:`maybe_snapshot`.

        A committed event must always be reported as stored: a snapshot/game
        -service failure here is logged and swallowed so it never turns a
        durably persisted event into an error (used by both the HTTP backfill
        path and the Valkey stream ingester).
        """
        try:
            return await self.maybe_snapshot(game_id, current_seq)
        except Exception:  # noqa: BLE001 - never fail a committed event
            logger.warning(
                "Snapshot after commit failed for game=%s at seq=%s (continuing)",
                game_id,
                current_seq,
                exc_info=True,
            )
            return None

    async def take_snapshot(self, game_id: str, snapshot_at_seq: int) -> StoredSnapshot:
        document = await self._game_service.get_snapshot(game_id)
        stored = await self._repository.write_snapshot(
            game_id, snapshot_at_seq, document
        )
        logger.info("Stored snapshot for game=%s at seq=%s", game_id, snapshot_at_seq)
        return stored


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
