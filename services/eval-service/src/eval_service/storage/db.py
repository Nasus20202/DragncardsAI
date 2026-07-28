from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from eval_service.telemetry import instrument_sqlalchemy_engine


def create_engine(database_url: str) -> AsyncEngine:
    engine = create_async_engine(database_url, future=True)
    instrument_sqlalchemy_engine(engine)
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
