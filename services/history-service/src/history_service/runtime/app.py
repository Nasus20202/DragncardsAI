from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from history_service.api.routers import (
    events,
    games,
    meta,
    restore,
    snapshots,
    transfer,
)
from history_service.config import Settings
from history_service.integrations.game_service import GameServiceClient
from history_service.integrations.orchestrator import OrchestratorClient
from history_service.runtime.ingest import StreamIngester
from history_service.runtime.restore import RestoreService
from history_service.runtime.snapshots import SnapshotService
from history_service.storage.db import create_engine, create_session_factory
from history_service.storage.migrations import ensure_schema
from history_service.storage.repository import Repository
from history_service.storage.valkey import RespConnection
from history_service.telemetry import instrument_fastapi_app, shutdown_telemetry

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    repository: Repository | None = None,
    valkey: RespConnection | None = None,
    game_service_client: GameServiceClient | None = None,
    orchestrator_client: OrchestratorClient | None = None,
    snapshot_service: SnapshotService | None = None,
    restore_service: RestoreService | None = None,
    start_ingester: bool = True,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        created_engine = None
        created_valkey = None
        created_game_service_client = None
        created_orchestrator_client = None
        ingester_task = None

        if repository is None:
            logger.info(
                "Initializing repository with database %s",
                settings.history_database_url,
            )
            created_engine = create_engine(settings.history_database_url)
            await ensure_schema(created_engine)
            session_factory = create_session_factory(created_engine)
            app.state.repository = Repository(session_factory)
        else:
            app.state.repository = repository

        app.state.valkey = valkey or RespConnection.from_url(settings.valkey_url)
        if valkey is None:
            created_valkey = app.state.valkey

        app.state.game_service_client = game_service_client or GameServiceClient(
            settings.game_service_base_url
        )
        if game_service_client is None:
            created_game_service_client = app.state.game_service_client
        app.state.orchestrator_client = orchestrator_client or OrchestratorClient(
            settings.agent_orchestrator_base_url
        )
        if orchestrator_client is None:
            created_orchestrator_client = app.state.orchestrator_client
        app.state.snapshot_service = snapshot_service or SnapshotService(
            settings=settings,
            repository=app.state.repository,
            game_service=app.state.game_service_client,
        )
        app.state.restore_service = restore_service or RestoreService(
            repository=app.state.repository,
            game_service=app.state.game_service_client,
            orchestrator=app.state.orchestrator_client,
        )
        app.state.settings = settings
        app.state.ingester_running = False

        if start_ingester:
            ingester = StreamIngester(
                settings=settings,
                repository=app.state.repository,
                client=app.state.valkey,
                snapshots=app.state.snapshot_service,
            )
            app.state.ingester = ingester

            async def _run_ingester() -> None:
                app.state.ingester_running = True
                try:
                    await ingester.run_forever()
                finally:
                    app.state.ingester_running = False

            ingester_task = asyncio.create_task(_run_ingester())
            app.state.ingester_task = ingester_task
            logger.info("Stream ingester task started")

        try:
            yield
        finally:
            logger.info("Shutting down history-service")
            if ingester_task is not None:
                await app.state.ingester.stop()
                ingester_task.cancel()
                try:
                    await ingester_task
                except asyncio.CancelledError:
                    pass
            if created_game_service_client is not None:
                await created_game_service_client.aclose()
            if created_orchestrator_client is not None:
                await created_orchestrator_client.aclose()
            if created_valkey is not None:
                await created_valkey.aclose()
            if created_engine is not None:
                await created_engine.dispose()
            shutdown_telemetry()

    app = FastAPI(
        title="History Service",
        version="0.1.0",
        description="Durable per-game event store, snapshots, and restore.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    instrument_fastapi_app(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(meta.router)
    app.include_router(games.router)
    app.include_router(events.router)
    app.include_router(snapshots.router)
    app.include_router(restore.router)
    app.include_router(transfer.router)

    return app
