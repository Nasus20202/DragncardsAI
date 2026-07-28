from __future__ import annotations

import json
import zlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, delete, func, insert, literal, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import Text

from history_service.schemas.envelope import (
    EventEnvelope,
    StoredEvent,
    StoredSnapshot,
)
from history_service.schemas.transfer import BundleEvent, BundleSnapshot
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


@dataclass(frozen=True)
class ImportResult:
    """Counts and seq range written by an accepted bundle import."""

    game_id: str
    imported_events: int
    imported_snapshots: int
    first_seq: int | None
    last_seq: int | None


class GameHistoryExistsError(Exception):
    """The import target already has recorded history, so nothing was written."""


class DuplicateImportRecordError(Exception):
    """A bundle carried a duplicate event, so the whole import was rolled back."""


# Rows buffered per INSERT while importing. Bounds the resident slice of a bundle
# whose every event embeds a full board state, while keeping the round trips to
# the database proportional to the bundle size rather than to its event count.
IMPORT_INSERT_CHUNK = 100

#: Payload fields a *timeline* listing omits because they are unbounded in size.
#: ``state`` is the raw DragnCards room state, measured at ~450-470 KB per
#: ``game-service`` event (see ``eval_service.judge.state_view``), and
#: ``conversation_context`` is an agent move's whole captured conversation. A
#: few hundred events of either is tens of megabytes, so a listing that carries
#: them cannot be fast no matter how it is indexed. Both stay reachable per
#: event through ``GET /games/{game_id}/events``.
TIMELINE_OMITTED_PAYLOAD_KEYS = ("state", "conversation_context")

#: The two scalars kept out of the omitted ``state``: they are what the round and
#: phase labels are derived from (DragnCards ``roundNumber`` counts *completed*
#: rounds and ``stepId`` is a dotted Marvel Champions step id). They are read as
#: text and re-attached under ``payload["state"]["game"]``, i.e. a projection of
#: the recorded state with its shape preserved, never a substitute for it.
_STATE_ROUND_PATH = ("state", "game", "roundNumber")
_STATE_STEP_PATH = ("state", "game", "stepId")


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

    async def list_event_summaries(
        self,
        game_id: str,
        *,
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[StoredEvent]:
        """Events by ascending ``seq`` with the unbounded payload fields removed.

        The pruning happens *in the database* rather than in Python, which is the
        whole point: the omitted fields are never deserialized into Python
        objects and never serialized into a response, so the cost of a page stops
        scaling with the size of the recorded game states. Measured on a
        400-event game with realistic ~466 KiB states, a page shrinks from 86 MiB
        to ~130 KiB.

        Each returned event is a :class:`StoredEvent` whose ``payload`` carries
        every field except :data:`TIMELINE_OMITTED_PAYLOAD_KEYS`, plus a
        two-scalar projection of ``state`` (see :data:`_STATE_ROUND_PATH`). It is
        deliberately the same type the full read returns, so callers render one
        shape; ``GET /games/{game_id}/events`` is where a complete payload comes
        from.
        """
        async with self._session_factory() as session:
            dialect = session.bind.dialect.name
            result = await session.execute(
                select(
                    EventRow.event_id,
                    EventRow.game_id,
                    EventRow.seq,
                    EventRow.envelope_version,
                    EventRow.actor,
                    EventRow.event_type,
                    EventRow.occurred_at,
                    EventRow.recorded_at,
                    EventRow.idempotency_key,
                    EventRow.producer_offset,
                    _pruned_payload(dialect).label("payload"),
                    _json_text_path(_STATE_ROUND_PATH).label("round_number"),
                    _json_text_path(_STATE_STEP_PATH).label("step_id"),
                )
                .where(EventRow.game_id == game_id, EventRow.seq > after_seq)
                .order_by(EventRow.seq.asc())
                .limit(limit)
            )
            return [_summary_to_stored_event(row) for row in result.all()]

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

    async def count_snapshots(self, game_id: str) -> int:
        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count())
                .select_from(SnapshotRow)
                .where(SnapshotRow.game_id == game_id)
            )
            return result.scalar_one()

    async def list_snapshots(
        self,
        game_id: str,
        *,
        after_seq: int = 0,
        limit: int | None = None,
    ) -> list[StoredSnapshot]:
        """A game's snapshots by ascending ``snapshot_at_seq``.

        ``after_seq``/``limit`` page the read for callers that must not hold
        every snapshot of a long game at once (each one is a full board state).
        Omitting both returns them all, which is what the snapshots endpoint and
        the cadence check want.
        """
        async with self._session_factory() as session:
            statement = (
                select(SnapshotRow)
                .where(
                    SnapshotRow.game_id == game_id,
                    SnapshotRow.snapshot_at_seq > after_seq,
                )
                .order_by(SnapshotRow.snapshot_at_seq.asc())
            )
            if limit is not None:
                statement = statement.limit(limit)
            result = await session.execute(statement)
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

    # -- import -------------------------------------------------------------

    async def import_game_history(
        self,
        game_id: str,
        records: AsyncIterator[BundleEvent | BundleSnapshot],
    ) -> ImportResult:
        """Persist a validated bundle under ``game_id`` in one transaction.

        Non-destructive: the target must have no recorded history. That check and
        the writes share one transaction, held under the same per-game advisory
        lock ``commit_event`` takes, so a concurrent import or a live ingest for
        the same game cannot slip between the check and the writes. Every field is
        written verbatim — ``seq``, ``event_id``, ``idempotency_key``,
        ``occurred_at`` and ``recorded_at`` included — so an imported game reads
        back identical to the game it was exported from rather than being
        re-sequenced or re-timestamped.

        ``records`` is consumed lazily while the transaction is open, so a
        producer that fails partway (a malformed line, an oversized body) aborts
        the transaction and leaves nothing behind. Callers therefore never
        observe a partial import.
        """
        imported_events = 0
        imported_snapshots = 0
        first_seq: int | None = None
        last_seq: int | None = None

        async with self._session_factory() as session:
            try:
                async with session.begin():
                    if session.bind.dialect.name == "postgresql":
                        await session.execute(
                            text("SELECT pg_advisory_xact_lock(:key)"),
                            {"key": _advisory_lock_key(game_id)},
                        )
                    existing = await session.execute(
                        select(EventRow.seq).where(EventRow.game_id == game_id).limit(1)
                    )
                    if existing.scalar_one_or_none() is not None:
                        raise GameHistoryExistsError(
                            f"game {game_id!r} already has recorded history; "
                            "import into a different game_id, or delete that "
                            "game's history first"
                        )

                    event_values: list[dict[str, Any]] = []
                    snapshot_values: list[dict[str, Any]] = []

                    async for record in records:
                        if isinstance(record, BundleEvent):
                            event_values.append(
                                {
                                    "event_id": record.event_id,
                                    "game_id": game_id,
                                    "seq": record.seq,
                                    "envelope_version": record.envelope_version,
                                    "actor": record.actor,
                                    "event_type": record.event_type,
                                    "payload_json": record.payload,
                                    "occurred_at": record.occurred_at,
                                    "recorded_at": record.recorded_at,
                                    "idempotency_key": record.idempotency_key,
                                    "producer_offset": (
                                        None
                                        if record.producer_offset is None
                                        else str(record.producer_offset)
                                    ),
                                }
                            )
                            imported_events += 1
                            if first_seq is None:
                                first_seq = record.seq
                            last_seq = record.seq
                            if len(event_values) >= IMPORT_INSERT_CHUNK:
                                await session.execute(insert(EventRow), event_values)
                                event_values = []
                        else:
                            snapshot_values.append(
                                {
                                    "game_id": game_id,
                                    "snapshot_at_seq": record.snapshot_at_seq,
                                    "snapshot_json": record.snapshot,
                                    "created_at": record.created_at,
                                }
                            )
                            imported_snapshots += 1
                            if len(snapshot_values) >= IMPORT_INSERT_CHUNK:
                                await session.execute(
                                    insert(SnapshotRow), snapshot_values
                                )
                                snapshot_values = []

                    if event_values:
                        await session.execute(insert(EventRow), event_values)
                    if snapshot_values:
                        await session.execute(insert(SnapshotRow), snapshot_values)
            except IntegrityError as exc:
                # The bundle violated a uniqueness constraint the store owns —
                # a repeated (game_id, idempotency_key) or (game_id, seq). The
                # transaction is already rolled back, so nothing was imported.
                raise DuplicateImportRecordError(
                    "bundle contains duplicate events (a repeated "
                    "idempotency_key or seq); nothing was imported"
                ) from exc

        return ImportResult(
            game_id=game_id,
            imported_events=imported_events,
            imported_snapshots=imported_snapshots,
            first_seq=first_seq,
            last_seq=last_seq,
        )

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


def _pruned_payload(dialect: str) -> ColumnElement[Any]:
    """``payload_json`` minus :data:`TIMELINE_OMITTED_PAYLOAD_KEYS`.

    Postgres removes a key from ``jsonb`` with the ``-`` operator (the column is
    ``JSONB``); sqlite, which stores JSON as text, uses ``json_remove``. Both are
    single-pass and neither needs the removed values to leave the database.
    """
    expression: ColumnElement[Any] = EventRow.payload_json
    if dialect == "postgresql":
        for key in TIMELINE_OMITTED_PAYLOAD_KEYS:
            expression = expression.op("-", return_type=JSON)(literal(key, Text))
        return expression
    return func.json_remove(
        expression,
        *(f"$.{key}" for key in TIMELINE_OMITTED_PAYLOAD_KEYS),
        type_=JSON,
    )


def _json_text_path(path: tuple[str, ...]) -> ColumnElement[Any]:
    """A nested ``payload_json`` value read as text.

    Text rather than a typed cast on purpose: ``stepId`` is a dotted string
    (``"0.1"``) that a JSON-typed read would silently turn into the float ``0.1``,
    and an integer cast of a malformed value would fail the whole query instead of
    yielding a missing label. Coercion happens in Python, where it can be lenient.
    """
    expression: Any = EventRow.payload_json
    for key in path:
        expression = expression[key]
    return expression.as_string()


def _as_json_object(value: Any) -> dict[str, Any]:
    """A payload read back from a pruning expression, as a dict.

    Drivers differ on whether a JSON-typed *expression* (as opposed to a column)
    comes back deserialized, so accept either and normalize. A payload that is
    not an object at all is reported as empty rather than raising: a listing must
    not fail because one recorded row is odd.
    """
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            decoded = json.loads(value)
        except TypeError, ValueError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _as_round_number(value: Any) -> int | None:
    """A round number read back as text, or None when it is missing or unusable.

    Lenient by design: a round label is worth losing over a malformed value, a
    listing is not. ``float`` is tried second because sqlite has no VARCHAR
    affinity and can hand a JSON number straight back as one.
    """
    if value is None:
        return None
    text_value = str(value)
    try:
        return int(text_value)
    except ValueError:
        pass
    try:
        return int(float(text_value))
    except ValueError:
        return None


def _summary_to_stored_event(row: Any) -> StoredEvent:
    payload = _as_json_object(row.payload)
    round_number = _as_round_number(row.round_number)
    step_id = None if row.step_id is None else str(row.step_id)
    if round_number is not None or step_id is not None:
        game: dict[str, Any] = {}
        if round_number is not None:
            game["roundNumber"] = round_number
        if step_id is not None:
            game["stepId"] = step_id
        payload["state"] = {"game": game}
    return StoredEvent(
        event_id=row.event_id,
        game_id=row.game_id,
        seq=row.seq,
        envelope_version=row.envelope_version,
        actor=row.actor,
        event_type=row.event_type,
        payload=payload,
        occurred_at=row.occurred_at,
        recorded_at=row.recorded_at,
        idempotency_key=row.idempotency_key,
        producer_offset=_coerce_offset(row.producer_offset),
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
