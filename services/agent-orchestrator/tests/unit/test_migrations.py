from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from agent_orchestrator.schema_migrations import runner
from agent_orchestrator.storage.db import create_engine


def test_split_statements_discards_empty_entries():
    assert runner._split_statements(" ; SELECT 1;\n\nSELECT 2 ; ; ") == [
        "SELECT 1",
        "SELECT 2",
    ]


def test_migration_applied_at_depends_on_dialect():
    sqlite_value = runner._migration_applied_at("sqlite")
    postgres_value = runner._migration_applied_at("postgresql")

    assert isinstance(sqlite_value, str)
    assert isinstance(postgres_value, datetime)
    assert postgres_value.tzinfo is None


def test_load_versioned_sql_prefers_dialect_and_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "0001_initial.sqlite.sql").write_text("sqlite version", encoding="utf-8")
    (sql_dir / "0002_extra.sql").write_text("generic version", encoding="utf-8")
    monkeypatch.setattr(runner, "SQL_DIR", sql_dir)

    assert runner._load_versioned_sql("0001_initial", "sqlite") == "sqlite version"
    assert runner._load_versioned_sql("0002_extra", "postgresql") == "generic version"


def test_discover_migrations_reads_versions_from_sql_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    sql_dir = tmp_path / "sql"
    sql_dir.mkdir()
    (sql_dir / "0000_schema_migrations.sql").write_text("bootstrap", encoding="utf-8")
    (sql_dir / "0002_extra.sqlite.sql").write_text("sqlite version", encoding="utf-8")
    (sql_dir / "0002_extra.postgresql.sql").write_text(
        "postgres version", encoding="utf-8"
    )
    (sql_dir / "0001_initial.sql").write_text("generic version", encoding="utf-8")
    monkeypatch.setattr(runner, "SQL_DIR", sql_dir)

    assert runner._discover_migrations() == ("0001_initial", "0002_extra")


@pytest.mark.asyncio
async def test_ensure_schema_is_idempotent(tmp_path: Path):
    database_path = tmp_path / "migrations.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    try:
        await runner.ensure_schema(engine)
        await runner.ensure_schema(engine)

        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text("SELECT version FROM schema_migrations ORDER BY version")
                )
            ).all()
    finally:
        await engine.dispose()

    assert rows == [(version,) for version in runner.MIGRATIONS]
