from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from history_service.schemas.envelope import (
    EventEnvelope,
    StoredEvent,
    StoredSnapshot,
)
from history_service.storage.models import EventRow, SnapshotRow, utc_now


@dataclass(frozen=True)
class CommitResult:
    """Outcome of an idempotent commit."""

    event: StoredEvent
    inserted: bool
    """True when a new row was written; False when the envelope was a duplicate."""


@dataclass(frozen=True)
class GameHistorySummary:
    """Aggregate stats for a single game that has recorded history."""

    game_id: str
    event_count: int
    first_recorded_at: datetime
    last_recorded_at: datetime


@dataclass(frozen=True)
class DeletionResult:
    """Counts removed when purging a game's history."""

    game_id: str
    deleted_events: int
    deleted_snapshots: int


def _advisory_lock_key(game_id: str) -> int:
    """Map a game id onto a signed 64-bit advisory lock key.

    The per-game key serializes ``seq`` assignment for one game while leaving
    other games free to proceed concurrently across replicas.
    """
    digest = zlib.crc32(game_id.encode("utf-8"))
    # Spread to 64-bit signed range expected by pg_advisory_xact_lock(bigint).
    return digest - 0x8000_0000


class Repository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    # -- ingestion / commit -------------------------------------------------

    async def commit_event(self, envelope: EventEnvelope) -> CommitResult:
        """Idempotently persist an envelope, assigning a gap-free per-game seq.

        Concurrency safety:
          * A per-game advisory lock (Postgres) serializes seq assignment for a
            single game so two replicas cannot mint the same seq.
          * The unique ``(game_id, idempotency_key)`` constraint + ON CONFLICT DO
            NOTHING makes duplicate deliveries store at most once, and a duplicate
            never consumes a seq (we re-read the existing row instead).
        """
        async with self._session_factory() as session:
            async with session.begin():
                dialect = session.bind.dialect.name
                if dialect == "postgresql":
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": _advisory_lock_key(envelope.game_id)},
                    )

                existing = await self._get_by_idempotency(
                    session, envelope.game_id, envelope.idempotency_key
                )
                if existing is not None:
                    return CommitResult(
                        event=_to_stored_event(existing), inserted=False
                    )

                next_seq = await self._next_seq(session, envelope.game_id)
                recorded_at = utc_now()
                values = {
                    "event_id": envelope.event_id,
                    "game_id": envelope.game_id,
                    "seq": next_seq,
                    "envelope_version": envelope.envelope_version,
                    "actor": envelope.actor,
                    "event_type": envelope.event_type,
                    "payload_json": envelope.payload,
                    "occurred_at": envelope.occurred_at,
                    "recorded_at": recorded_at,
                    "idempotency_key": envelope.idempotency_key,
                    "producer_offset": (
                        None
                        if envelope.producer_offset is None
                        else str(envelope.producer_offset)
                    ),
                }
                insert_stmt = (
                    pg_insert(EventRow)
                    if dialect == "postgresql"
                    else sqlite_insert(EventRow)
                )
                insert_stmt = insert_stmt.values(**values).on_conflict_do_nothing(
                    index_elements=["game_id", "idempotency_key"]
                )
                result = await session.execute(insert_stmt)

            inserted = (result.rowcount or 0) > 0

        if inserted:
            stored = StoredEvent(
                event_id=envelope.event_id,
                game_id=envelope.game_id,
                seq=next_seq,
                envelope_version=envelope.envelope_version,
                actor=envelope.actor,
                event_type=envelope.event_type,
                payload=envelope.payload,
                occurred_at=_as_utc(envelope.occurred_at),
                recorded_at=recorded_at,
                idempotency_key=envelope.idempotency_key,
                producer_offset=envelope.producer_offset,
            )
            return CommitResult(event=stored, inserted=True)

        # A concurrent insert won the race after our existence check; re-read.
        async with self._session_factory() as session:
            existing = await self._get_by_idempotency(
                session, envelope.game_id, envelope.idempotency_key
            )
        assert existing is not None
        return CommitResult(event=_to_stored_event(existing), inserted=False)

    async def _next_seq(self, session: AsyncSession, game_id: str) -> int:
        result = await session.execute(
            select(EventRow.seq)
            .where(EventRow.game_id == game_id)
            .order_by(EventRow.seq.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        return 1 if latest is None else latest + 1

    async def _get_by_idempotency(
        self, session: AsyncSession, game_id: str, idempotency_key: str
    ) -> EventRow | None:
        result = await session.execute(
            select(EventRow).where(
                EventRow.game_id == game_id,
                EventRow.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    # -- event reads --------------------------------------------------------

    async def get_latest_seq(self, game_id: str) -> int | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventRow.seq)
                .where(EventRow.game_id == game_id)
                .order_by(EventRow.seq.desc())
                .limit(1)
            )
            return result.scalar_one_or_none()

    async def count_events_since_seq(self, game_id: str, since_seq: int) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(EventRow)
                .where(EventRow.game_id == game_id, EventRow.seq > since_seq)
            )
            return result.scalar_one()

    async def list_events(
        self,
        game_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[StoredEvent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventRow)
                .where(EventRow.game_id == game_id, EventRow.seq > after_seq)
                .order_by(EventRow.seq.asc())
                .limit(limit)
            )
            return [_to_stored_event(row) for row in result.scalars().all()]

    async def list_games(self) -> list[GameHistorySummary]:
        """Summarize every game with recorded history in one grouped query.

        Uses a single ``GROUP BY game_id`` aggregation (count + min/max of
        ``recorded_at``) so the cost is one query regardless of game count,
        avoiding any per-game fan-out. Ordered by most recent activity.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(
                    EventRow.game_id,
                    func.count().label("event_count"),
                    func.min(EventRow.recorded_at).label("first_recorded_at"),
                    func.max(EventRow.recorded_at).label("last_recorded_at"),
                )
                .group_by(EventRow.game_id)
                .order_by(func.max(EventRow.recorded_at).desc())
            )
            return [
                GameHistorySummary(
                    game_id=row.game_id,
                    event_count=row.event_count,
                    first_recorded_at=_as_utc(row.first_recorded_at),
                    last_recorded_at=_as_utc(row.last_recorded_at),
                )
                for row in result.all()
            ]

    async def get_events_in_range(
        self, game_id: str, *, low_exclusive: int, high_inclusive: int
    ) -> list[StoredEvent]:
        """Events with ``low_exclusive < seq <= high_inclusive`` ascending."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventRow)
                .where(
                    EventRow.game_id == game_id,
                    EventRow.seq > low_exclusive,
                    EventRow.seq <= high_inclusive,
                )
                .order_by(EventRow.seq.asc())
            )
            return [_to_stored_event(row) for row in result.scalars().all()]

    async def get_earliest_state_event(self, game_id: str) -> StoredEvent | None:
        """The first game-state event for a game (the branch's plugin source).

        Game-state events carry the session ``plugin_name``, so the earliest one
        lets a branchable restore materialize a fresh session even when no
        snapshot has been taken yet.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventRow)
                .where(
                    EventRow.game_id == game_id,
                    EventRow.actor == "game-service",
                )
                .order_by(EventRow.seq.asc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_stored_event(row) if row is not None else None

    async def get_latest_state_event_at_or_before(
        self, game_id: str, target_seq: int
    ) -> StoredEvent | None:
        """The most recent game-state event at/<= ``target_seq``.

        Each game-state event payload carries the complete game state, so the
        nearest one is a dense, always-available reconstruction base — used when
        no periodic snapshot exists (or is older than this event).
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventRow)
                .where(
                    EventRow.game_id == game_id,
                    EventRow.actor == "game-service",
                    EventRow.seq <= target_seq,
                )
                .order_by(EventRow.seq.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_stored_event(row) if row is not None else None

    async def get_latest_agent_event_at_or_before(
        self, game_id: str, target_seq: int
    ) -> StoredEvent | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EventRow)
                .where(
                    EventRow.game_id == game_id,
                    EventRow.actor == "agent",
                    EventRow.seq <= target_seq,
                )
                .order_by(EventRow.seq.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_stored_event(row) if row is not None else None

    # -- snapshots ----------------------------------------------------------

    async def write_snapshot(
        self, game_id: str, snapshot_at_seq: int, snapshot: dict[str, Any]
    ) -> StoredSnapshot:
        async with self._session_factory() as session:
            async with session.begin():
                dialect = session.bind.dialect.name
                created_at = utc_now()
                insert_stmt = (
                    pg_insert(SnapshotRow)
                    if dialect == "postgresql"
                    else sqlite_insert(SnapshotRow)
                )
                insert_stmt = insert_stmt.values(
                    game_id=game_id,
                    snapshot_at_seq=snapshot_at_seq,
                    snapshot_json=snapshot,
                    created_at=created_at,
                ).on_conflict_do_nothing(index_elements=["game_id", "snapshot_at_seq"])
                await session.execute(insert_stmt)
        return StoredSnapshot(
            game_id=game_id,
            snapshot_at_seq=snapshot_at_seq,
            snapshot=snapshot,
            created_at=created_at,
        )

    async def list_snapshots(self, game_id: str) -> list[StoredSnapshot]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SnapshotRow)
                .where(SnapshotRow.game_id == game_id)
                .order_by(SnapshotRow.snapshot_at_seq.asc())
            )
            return [_to_stored_snapshot(row) for row in result.scalars().all()]

    async def get_latest_snapshot_at_or_before(
        self, game_id: str, target_seq: int
    ) -> StoredSnapshot | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SnapshotRow)
                .where(
                    SnapshotRow.game_id == game_id,
                    SnapshotRow.snapshot_at_seq <= target_seq,
                )
                .order_by(SnapshotRow.snapshot_at_seq.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return _to_stored_snapshot(row) if row is not None else None

    # -- deletion -----------------------------------------------------------

    async def delete_game_history(self, game_id: str) -> DeletionResult:
        """Purge all history for a game (events + snapshots) in one transaction.

        Per-game producer-offset bookkeeping lives on the ``producer_offset``
        column of each event row, so it is removed together with the events; no
        separate per-game offset table exists. Idempotent: a game with no
        history yields zero counts (and no error). Both deletes share a single
        transaction so a partial purge can never be observed.
        """
        async with self._session_factory() as session:
            async with session.begin():
                events_result = await session.execute(
                    delete(EventRow).where(EventRow.game_id == game_id)
                )
                snapshots_result = await session.execute(
                    delete(SnapshotRow).where(SnapshotRow.game_id == game_id)
                )
        return DeletionResult(
            game_id=game_id,
            deleted_events=events_result.rowcount or 0,
            deleted_snapshots=snapshots_result.rowcount or 0,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _coerce_offset(value: str | None) -> int | str | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return value


def _to_stored_event(row: EventRow) -> StoredEvent:
    return StoredEvent(
        event_id=row.event_id,
        game_id=row.game_id,
        seq=row.seq,
        envelope_version=row.envelope_version,
        actor=row.actor,
        event_type=row.event_type,
        payload=row.payload_json,
        occurred_at=row.occurred_at,
        recorded_at=row.recorded_at,
        idempotency_key=row.idempotency_key,
        producer_offset=_coerce_offset(row.producer_offset),
    )


def _to_stored_snapshot(row: SnapshotRow) -> StoredSnapshot:
    return StoredSnapshot(
        game_id=row.game_id,
        snapshot_at_seq=row.snapshot_at_seq,
        snapshot=row.snapshot_json,
        created_at=row.created_at,
    )
