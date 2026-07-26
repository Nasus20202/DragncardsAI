from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from dragncards_common.schema_migrations import discover_migrations, ensure_schema

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def _write_sql_dir(tmp_path: Path) -> Path:
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "0000_schema_migrations.sql").write_text(_BOOTSTRAP, encoding="utf-8")
    (sql_dir / "0001_widgets.sql").write_text(
        "CREATE TABLE widgets (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    (sql_dir / "0002_gadgets.sql").write_text(
        "CREATE TABLE gadgets (id INTEGER PRIMARY KEY);", encoding="utf-8"
    )
    return sql_dir


def test_discover_migrations_orders_and_excludes_bootstrap(tmp_path: Path):
    sql_dir = _write_sql_dir(tmp_path)
    assert discover_migrations(sql_dir) == ("0001_widgets", "0002_gadgets")


async def test_ensure_schema_applies_and_is_idempotent(tmp_path: Path):
    sql_dir = _write_sql_dir(tmp_path)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        await ensure_schema(engine, sql_dir)
        await ensure_schema(engine, sql_dir)  # second run is a no-op
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version FROM schema_migrations"))
            versions = sorted(row[0] for row in result)
        assert versions == ["0001_widgets", "0002_gadgets"]
    finally:
        await engine.dispose()
