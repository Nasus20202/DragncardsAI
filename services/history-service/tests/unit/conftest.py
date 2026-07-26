from __future__ import annotations

from datetime import datetime, timezone

import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from history_service.schemas.envelope import EventEnvelope
from history_service.storage.db import create_session_factory
from history_service.storage.migrations import ensure_schema
from history_service.storage.repository import Repository


@pytest_asyncio.fixture
async def repository():
    """A repository backed by a shared in-memory sqlite database.

    ``StaticPool`` keeps a single underlying connection so every session in the
    test sees the same in-memory schema and data.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    factory = create_session_factory(engine)
    try:
        yield Repository(factory)
    finally:
        await engine.dispose()


def make_envelope(
    game_id: str,
    *,
    actor: str = "game-service",
    producer_offset: int | str = 0,
    event_type: str = "state",
    payload: dict | None = None,
    occurred_at: datetime | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        game_id=game_id,
        actor=actor,
        event_type=event_type,
        payload=payload or {},
        occurred_at=occurred_at or datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:{actor}:{producer_offset}",
        producer_offset=producer_offset,
    )
