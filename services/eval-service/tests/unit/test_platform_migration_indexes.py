from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
import pytest

from eval_service.schema_migrations import ensure_schema


async def _index_columns(connection, name: str) -> list[str]:
    result = await connection.execute(text(f"PRAGMA index_info('{name}')"))
    return [row[2] for row in result.fetchall()]


@pytest.mark.asyncio
async def test_sqlite_platform_migration_scopes_game_indexes():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        await ensure_schema(engine)
        async with engine.connect() as connection:
            assert await _index_columns(
                connection, "ix_evaluation_requests_game_id"
            ) == ["game_id", "platform"]
            assert await _index_columns(connection, "ix_evaluated_targets_game_id") == [
                "game_id",
                "platform",
            ]
    finally:
        await engine.dispose()
