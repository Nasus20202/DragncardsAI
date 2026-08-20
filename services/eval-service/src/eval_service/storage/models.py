from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Non-terminal target statuses: a request is still in progress while any of its
# targets is pending or running. Canonical home so storage queries and the
# runtime status aggregation share one definition.
NON_TERMINAL_STATUSES: frozenset[str] = frozenset({"pending", "running"})


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


class EvaluationRequestRow(Base):
    """A user-submitted on-demand evaluation request.

    One request expands into one or more :class:`EvaluatedTargetRow` rows linked
    by ``request_id``. Status is derived from its targets at read time.
    """

    __tablename__ = "evaluation_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(
        String(32), nullable=False, default="dragncards", index=True
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    selection_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    force: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The effective (merged) judge config for this request, used by the worker
    # and stream. NULL means "use server defaults".
    judge_config_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now
    )


class EvaluatedTargetRow(Base):
    """An evaluated (or to-be-evaluated) target keyed by (game, seq, scope, player).

    The UNIQUE ``(game_id, target_seq, scope, player)`` constraint is the durable
    at-most-once dedupe substrate: a claim via ``INSERT ... ON CONFLICT DO
    NOTHING`` guarantees only one worker evaluates a given target. ``force``
    re-evaluation overwrites the existing row's verdict / status in place.
    ``player`` is part of the key so per-player round/game targets that share a
    closing ``target_seq`` (one per acting player) each get their own row; it is
    stored as ``''`` for legacy/unattributed targets so NULL never widens the
    key (NULLs compare distinct under UNIQUE).
    """

    __tablename__ = "evaluated_targets"
    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "platform",
            "target_seq",
            "scope",
            "player",
            name="uq_targets_game_seq_scope_player",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("evaluation_requests.request_id"), nullable=False
    )
    game_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(
        String(32), nullable=False, default="dragncards", index=True
    )
    target_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    # Player this target scores (e.g. ``player1``); ``''`` when unattributed.
    player: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    round_from_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    round_to_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # The CLAIM EPOCH and the retry counter, in one monotonic integer: every
    # claim (a drain claim, or a ``force`` re-claim) increments it, so every
    # claim is both a new attempt and a new epoch.
    #
    # As an epoch it is what makes a terminal write safe. ``status='running'``
    # alone answers "is this row running?", never "is this row still running
    # under MY claim?" -- so a worker whose claim was revoked mid-evaluation
    # (reclaimed after its lease expired, or force-reset) would find the row
    # ``running`` again under someone else's claim and overwrite their verdict
    # with its own abandoned one. Terminal writes therefore guard on
    # ``status='running' AND attempts = :claimed``; a revoked claim's write
    # matches no rows and is discarded, which is correct.
    #
    # As a counter it is the poison guard: a target whose ``attempts`` exceeds
    # ``EVAL_MAX_ATTEMPTS`` is marked ``failed`` instead of being reclaimed
    # again, because a target that reliably kills its worker spends judge budget
    # on every pass and would otherwise loop forever.
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    verdict_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # The effective judge config to evaluate THIS target with (snapshot of the
    # request's config). NULL means "use server defaults".
    judge_config_json: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utc_now
    )
