from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_orchestrator.api.routers import catalog, context, jobs, meta, sessions
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient
from agent_orchestrator.integrations.mcp.client import StreamableHttpMcpClient
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import (
    InMemoryLiveEventBus,
    LiveEventBus,
    ValkeyLiveEventBus,
)
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.worker import WorkerService
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository
from agent_orchestrator.telemetry import instrument_fastapi_app, shutdown_telemetry

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    repository: Repository | None = None,
    bifrost_client: BifrostClient | None = None,
    live_event_bus: LiveEventBus | None = None,
    mcp_client: StreamableHttpMcpClient | None = None,
    skill_registry: SkillRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        created_engine = None
        created_bifrost = None
        created_live_event_bus = None
        worker_task = None

        if repository is None:
            logger.info(
                "Initializing repository with database %s", settings.database_url
            )
            created_engine = create_engine(settings.database_url)
            await ensure_schema(created_engine)
            session_factory = create_session_factory(created_engine)
            app.state.repository = Repository(session_factory)
        else:
            logger.info("Using injected repository")
            app.state.repository = repository

        if bifrost_client is None:
            logger.info("Initializing Bifrost client for %s", settings.bifrost_url)
            created_bifrost = BifrostClient(
                settings.bifrost_url,
                settings.bifrost_api_key,
                settings.provider_prefixes,
                models_cache_ttl_seconds=settings.provider_models_cache_ttl_seconds,
            )
            app.state.bifrost_client = created_bifrost
        else:
            logger.info("Using injected Bifrost client")
            app.state.bifrost_client = bifrost_client

        if live_event_bus is None:
            logger.info(
                "Initializing Valkey live event bus for %s", settings.valkey_url
            )
            created_live_event_bus = ValkeyLiveEventBus(settings.valkey_url)
            app.state.live_event_bus = created_live_event_bus
        else:
            logger.info("Using injected live event bus")
            app.state.live_event_bus = live_event_bus

        app.state.settings = settings
        app.state.skill_registry = skill_registry or SkillRegistry(settings.skill_roots)
        logger.info(
            "Skill roots: %s", ", ".join(str(root) for root in settings.skill_roots)
        )
        app.state.mcp_client = mcp_client or StreamableHttpMcpClient(
            timeout_seconds=settings.mcp_request_timeout_seconds,
        )
        app.state.mcp_tool_catalog = McpToolCatalog(app.state.mcp_client)
        app.state.worker = WorkerService(
            settings=settings,
            repository=app.state.repository,
            bifrost_client=app.state.bifrost_client,
            live_event_bus=app.state.live_event_bus,
            mcp_tool_catalog=app.state.mcp_tool_catalog,
            skill_registry=app.state.skill_registry,
        )
        worker_task = asyncio.create_task(app.state.worker.run_forever())
        app.state.worker_task = worker_task
        logger.info("Worker task started")
        try:
            yield
        finally:
            logger.info("Shutting down agent-orchestrator")
            await app.state.worker.stop()
            if worker_task is not None:
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            if created_bifrost is not None:
                await created_bifrost.aclose()
            if created_live_event_bus is not None:
                await created_live_event_bus.aclose()
            if created_engine is not None:
                await created_engine.dispose()
            shutdown_telemetry()

    app = FastAPI(
        title="Agent Orchestrator",
        version="0.1.0",
        description="Background-job harness for LLM-driven DragnCards agents.",
        lifespan=lifespan,
    )
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
    app.include_router(catalog.router)
    app.include_router(sessions.router)
    app.include_router(jobs.router)
    app.include_router(context.router)

    return app
