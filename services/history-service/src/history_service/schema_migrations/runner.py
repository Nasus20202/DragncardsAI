from __future__ import annotations

from pathlib import Path

from dragncards_common.schema_migrations import discover_migrations
from dragncards_common.schema_migrations import ensure_schema as _ensure_schema
from sqlalchemy.ext.asyncio import AsyncEngine

SQL_DIR = Path(__file__).with_name("sql")

MIGRATIONS = discover_migrations(SQL_DIR)


async def ensure_schema(engine: AsyncEngine) -> None:
    await _ensure_schema(engine, SQL_DIR, MIGRATIONS)
