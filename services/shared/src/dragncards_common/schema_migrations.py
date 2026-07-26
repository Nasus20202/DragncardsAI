"""Shared SQL schema-migration runner.

Every backend service that owns a PostgreSQL/SQLite schema versions it with a
directory of ``NNNN_name.sql`` files plus a ``0000_schema_migrations.sql``
bootstrap. The runner logic (dialect-aware SQL loading, the ``schema_migrations``
ledger table, applied-version bookkeeping) is identical across services; only the
SQL directory differs. Callers pass their own ``sql_dir``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

_BOOTSTRAP_FILENAME = "0000_schema_migrations.sql"


def discover_migrations(sql_dir: Path) -> tuple[str, ...]:
    """Return the sorted migration versions found in ``sql_dir``.

    A version is the leading ``NNNN`` segment of each ``*.sql`` file, excluding
    the ``0000_schema_migrations.sql`` bootstrap. Dialect-specific variants
    (``NNNN.postgresql.sql`` / ``NNNN.sqlite.sql``) collapse to a single version.
    """
    versions = {
        sql_file.name.split(".", 1)[0]
        for sql_file in sql_dir.glob("*.sql")
        if sql_file.name != _BOOTSTRAP_FILENAME
    }
    return tuple(sorted(versions))


async def ensure_schema(
    engine: AsyncEngine,
    sql_dir: Path,
    migrations: tuple[str, ...] | None = None,
) -> None:
    """Apply any not-yet-applied migrations from ``sql_dir`` against ``engine``.

    ``migrations`` may be supplied to reuse a precomputed version tuple; when
    omitted it is discovered from ``sql_dir``.
    """
    if migrations is None:
        migrations = discover_migrations(sql_dir)
    async with engine.begin() as conn:
        await _execute_sql(conn, _load_sql(sql_dir, _BOOTSTRAP_FILENAME))
        result = await conn.execute(text("SELECT version FROM schema_migrations"))
        applied = {row[0] for row in result}
        for version in migrations:
            if version in applied:
                continue
            await _execute_sql(
                conn, _load_versioned_sql(sql_dir, version, engine.dialect.name)
            )
            await conn.execute(
                text(
                    "INSERT INTO schema_migrations (version, applied_at) "
                    "VALUES (:version, :applied_at)"
                ),
                {
                    "version": version,
                    "applied_at": _migration_applied_at(engine.dialect.name),
                },
            )


def _load_versioned_sql(sql_dir: Path, version: str, dialect_name: str) -> str:
    filename = f"{version}.{dialect_name}.sql"
    if (sql_dir / filename).exists():
        return _load_sql(sql_dir, filename)
    return _load_sql(sql_dir, f"{version}.sql")


def _load_sql(sql_dir: Path, filename: str) -> str:
    return (sql_dir / filename).read_text(encoding="utf-8")


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
