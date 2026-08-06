from __future__ import annotations

import os
from urllib.parse import quote
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from eval_service.schema_migrations import ensure_schema
from eval_service.storage.db import create_engine, create_session_factory
from eval_service.storage.repository import Repository

POSTGRES_URL = os.environ.get(
    "EVAL_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5443/eval_service",
)


def _database_url(database_name: str) -> str:
    return (
        make_url(POSTGRES_URL)
        .set(database=database_name)
        .render_as_string(hide_password=False)
    )


async def _postgres_available() -> bool:
    engine = create_async_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _create_database(database_name: str) -> None:
    admin_engine = create_async_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(
                text(f'CREATE DATABASE "{quote(database_name, safe="_")}"')
            )
    finally:
        await admin_engine.dispose()


async def _drop_database(database_name: str) -> None:
    admin_engine = create_async_engine(
        _database_url("postgres"), isolation_level="AUTOCOMMIT"
    )
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(
                text("""
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :database_name AND pid <> pg_backend_pid()
                    """),
                {"database_name": database_name},
            )
            await conn.execute(
                text(f'DROP DATABASE IF EXISTS "{quote(database_name, safe="_")}"')
            )
    finally:
        await admin_engine.dispose()


@pytest_asyncio.fixture
async def postgres_repository():
    if not await _postgres_available():
        pytest.skip("PostgreSQL not reachable for integration tests")
    database_name = f"eval_service_test_{uuid4().hex}"
    await _create_database(database_name)
    engine = create_engine(_database_url(database_name))
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))
    try:
        yield repository
    finally:
        await engine.dispose()
        await _drop_database(database_name)


@pytest_asyncio.fixture
async def postgres_repository_factory():
    """Build independent repositories against ONE throwaway database.

    Each call returns a repository on its OWN engine, and therefore its own
    connection pool. A claim race has to be run over genuinely separate database
    sessions to mean anything -- that is the exact configuration the advisory
    lock exists to serialize, and it is what distinguishes two replicas from two
    coroutines sharing one connection.
    """
    if not await _postgres_available():
        pytest.skip("PostgreSQL not reachable for integration tests")
    database_name = f"eval_service_test_{uuid4().hex}"
    await _create_database(database_name)
    url = _database_url(database_name)
    engines = []

    async def make_repository() -> Repository:
        engine = create_engine(url)
        if not engines:
            await ensure_schema(engine)
        engines.append(engine)
        return Repository(create_session_factory(engine))

    try:
        yield make_repository
    finally:
        for engine in engines:
            await engine.dispose()
        await _drop_database(database_name)
