from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


MIGRATIONS = ("0001_initial", "0002_context_management")
SQL_DIR = Path(__file__).with_name("sql")


async def ensure_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await _execute_sql(conn, _load_sql("0000_schema_migrations.sql"))
        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied = {row[0] for row in result}
        for version in MIGRATIONS:
            if version in applied:
                continue
            await _execute_sql(conn, _load_versioned_sql(version, engine.dialect.name))
            await conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (:version, :applied_at)"
                ),
                {
                    "version": version,
                    "applied_at": _migration_applied_at(engine.dialect.name),
                },
            )


def _load_versioned_sql(version: str, dialect_name: str) -> str:
    filename = f"{version}.{dialect_name}.sql"
    if (SQL_DIR / filename).exists():
        return _load_sql(filename)
    return _load_sql(f"{version}.sql")


def _load_sql(filename: str) -> str:
    return (SQL_DIR / filename).read_text(encoding="utf-8")


def _migration_applied_at(dialect_name: str) -> str | datetime:
    value = datetime.now(timezone.utc)
    if dialect_name == "sqlite":
        return value.isoformat()
    return value.replace(tzinfo=None)


async def _execute_sql(conn: AsyncConnection, script: str) -> None:
    for statement in _split_statements(script):
        await conn.exec_driver_sql(statement)


def _split_statements(script: str) -> list[str]:
    return [statement.strip() for statement in script.split(";") if statement.strip()]
