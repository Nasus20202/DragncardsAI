from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from history_service.config import Settings
from history_service.runtime.ingest import StreamIngester, publish_envelope
from history_service.schemas.envelope import EventEnvelope


def _envelope(game_id: str, offset: int):
    return EventEnvelope(
        game_id=game_id,
        actor="game-service",
        event_type="state",
        payload={"offset": offset},
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:game-service:{offset}",
        producer_offset=offset,
    )


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.valkey
async def test_ingest_from_real_valkey_stream(postgres_repository, valkey_connection):
    stream = f"history:ingest:test:{uuid4().hex}"
    group = "history-service"
    settings = Settings(
        history_ingest_stream=stream,
        history_ingest_consumer_group=group,
        history_ingest_consumer_name="test-consumer",
    )
    ingester = StreamIngester(
        settings=settings, repository=postgres_repository, client=valkey_connection
    )
    await ingester.ensure_group()
    try:
        await publish_envelope(
            valkey_connection, stream, _envelope("g1", 0), maxlen=1000
        )
        # Duplicate delivery of the same envelope.
        await publish_envelope(
            valkey_connection, stream, _envelope("g1", 0), maxlen=1000
        )
        await publish_envelope(
            valkey_connection, stream, _envelope("g1", 1), maxlen=1000
        )

        processed = 0
        for _ in range(5):
            processed += await ingester.process_batch()
            if processed >= 3:
                break

        events = await postgres_repository.list_events("g1")
        # Three deliveries, but the duplicate collapses -> 2 stored events.
        assert [e.seq for e in events] == [1, 2]
    finally:
        await valkey_connection.execute("DEL", stream)
