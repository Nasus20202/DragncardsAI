from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetime that round-trips through sqlite and Postgres."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(
        self, value: datetime | None, dialect
    ) -> str | datetime | None:
        if value is None:
            return None
        normalized = (
            value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        )
        normalized = normalized.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return normalized.isoformat()
        return normalized

    def process_result_value(
        self, value: str | datetime | None, dialect
    ) -> datetime | None:
        if value is None:
            return None
        parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    """Append-only per-game event log entry.

    ``seq`` is assigned authoritatively by the history-service at commit time and
    is gap-free per ``game_id`` starting at 1. ``(game_id, idempotency_key)`` is
    unique so at-least-once duplicates collapse to a single stored row.
    """

    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "game_id", "idempotency_key", name="uq_events_game_idempotency"
        ),
        UniqueConstraint("game_id", "seq", name="uq_events_game_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    envelope_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    producer_offset: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SnapshotRow(Base):
    """A full game-state checkpoint tied to the ``seq`` it corresponds to."""

    __tablename__ = "snapshots"
    __table_args__ = (
        UniqueConstraint("game_id", "snapshot_at_seq", name="uq_snapshots_game_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    snapshot_at_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now
    )
