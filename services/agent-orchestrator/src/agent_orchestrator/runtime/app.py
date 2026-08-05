from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_orchestrator.api.routers import (
    catalog,
    context,
    jobs,
    meta,
    personas,
    players,
    sessions,
)
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient
from agent_orchestrator.integrations.mcp.client import McpClient
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.history_emitter import (
    HistoryEventBus,
    HistoryEventEmitter,
    ValkeyHistoryEventBus,
)
from agent_orchestrator.runtime.live_event_resilience import (
    best_effort_live_event_bus,
)
from agent_orchestrator.runtime.live_events import (
    LiveEventBus,
    ValkeyLiveEventBus,
)
from agent_orchestrator.runtime.job_event_stream import JobEventStreamService
from agent_orchestrator.runtime.request_limits import MaxBodySizeMiddleware
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.worker import WorkerService
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository
from agent_orchestrator.storage.valkey import RespConnection
from agent_orchestrator.telemetry import instrument_fastapi_app, shutdown_telemetry

logger = logging.getLogger(__name__)


async def _ensure_default_mcp_registry(repo: Repository, settings: Settings) -> None:
    """Ensure default game-service MCP exists in registry and matches settings."""
    if not settings.default_game_service_mcp_enabled:
        return

    existing = await repo.get_mcp_registry(settings.default_game_service_mcp_name)
    if existing is None:
        logger.info(
            "Creating default %s MCP in registry",
            settings.default_game_service_mcp_name,
        )
    elif (
        existing.transport != settings.default_game_service_mcp_transport
        or existing.server_url != settings.game_service_mcp_url.rstrip("/") + "/"
        or existing.headers_json != {}
        or existing.custom
    ):
        logger.info(
            "Updating default %s MCP in registry from settings",
            settings.default_game_service_mcp_name,
        )
    else:
        return

    await repo.add_mcp_registry(
        name=settings.default_game_service_mcp_name,
        transport=settings.default_game_service_mcp_transport,
        server_url=settings.game_service_mcp_url,
        headers_json=None,
        custom=False,
    )


async def _sync_skill_registry(repo: Repository, registry: SkillRegistry) -> None:
    """
    Mirror the on-disk skills into the persistent `skill_registries` table.

    Enabling a skill for a session needs a registry row (the session/skill join
    is a foreign key), and rows used to appear only as a side effect of the
    enable-by-POST route. That left the table a partial, stale view of the skill
    roots: a skill shipped on disk but never enabled through that one route
    could not be enabled at all. Syncing at boot makes the table reflect the
    filesystem instead. Upsert-only — rows for skills that are no longer on disk
    are kept so existing session assignments keep their foreign key.
    """
    definitions = registry.list_skills()
    for name, definition in sorted(definitions.items()):
        await repo.add_skill_registry(
            name=name,
            skill_path=str(definition.path),
            description=definition.description,
            metadata_json=dict(definition.metadata),
        )
    logger.info("Synced %d on-disk skills into the skill registry", len(definitions))


def create_app(
    *,
    settings: Settings | None = None,
    repository: Repository | None = None,
    bifrost_client: BifrostClient | None = None,
    live_event_bus: LiveEventBus | None = None,
    mcp_client: McpClient | None = None,
    skill_registry: SkillRegistry | None = None,
    history_event_bus: HistoryEventBus | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        created_engine = None
        created_bifrost = None
        created_live_event_bus = None
        created_valkey_conn = None
        created_history_event_bus = None
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
            parsed = urlparse(settings.valkey_url)
            # A dedicated RespConnection is created for BifrostClient's model cache.
            # ValkeyLiveEventBus manages its own internal connection.  Both point at
            # the same Valkey server; they are kept separate because the two subsystems
            # have independent lifecycles and RespConnection is stateless (per-command TCP).
            created_valkey_conn = RespConnection(
                parsed.hostname or "localhost", parsed.port or 6379
            )
            created_bifrost = BifrostClient(
                settings.bifrost_url,
                settings.bifrost_api_key,
                settings.provider_prefixes,
                models_cache_ttl_seconds=settings.provider_models_cache_ttl_seconds,
                list_models_timeout_seconds=settings.bifrost_list_models_timeout_seconds,
                unavailable_cache_ttl_seconds=settings.bifrost_unavailable_cache_ttl_seconds,
                unavailable_retryable_cache_ttl_seconds=settings.bifrost_unavailable_retryable_cache_ttl_seconds,
                valkey=created_valkey_conn,
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
            resolved_live_event_bus: LiveEventBus = created_live_event_bus
        else:
            logger.info("Using injected live event bus")
            resolved_live_event_bus = live_event_bus
        # Everything in the running service reads its bus from here — the worker,
        # the API routers, the SSE stream — so wrapping once makes every publish
        # in the process best-effort. A transient Valkey error then costs a
        # browser some latency instead of costing a job its run (DRA-42).
        app.state.live_event_bus = best_effort_live_event_bus(resolved_live_event_bus)

        app.state.settings = settings
        app.state.skill_registry = skill_registry or SkillRegistry(settings.skill_roots)
        logger.info(
            "Skill roots: %s", ", ".join(str(root) for root in settings.skill_roots)
        )
        app.state.mcp_client = mcp_client or McpClient(
            timeout_seconds=settings.mcp_request_timeout_seconds,
        )
        app.state.mcp_tool_catalog = McpToolCatalog(app.state.mcp_client)
        # Initialize default game-service MCP
        await _ensure_default_mcp_registry(app.state.repository, settings)
        await _sync_skill_registry(app.state.repository, app.state.skill_registry)
        app.state.job_event_stream = JobEventStreamService(
            repository=app.state.repository,
            live_event_bus=app.state.live_event_bus,
            idle_block_seconds=settings.job_event_stream_idle_block_seconds,
        )

        if history_event_bus is None and settings.history_ingest_enabled:
            logger.info(
                "Initializing Valkey history event bus stream=%s",
                settings.history_ingest_stream,
            )
            created_history_event_bus = ValkeyHistoryEventBus(
                settings.effective_history_valkey_url,
                stream_key=settings.history_ingest_stream,
                max_stream_length=settings.history_ingest_stream_maxlen,
            )
            resolved_history_bus: HistoryEventBus | None = created_history_event_bus
        else:
            resolved_history_bus = history_event_bus
        app.state.history_event_bus = resolved_history_bus
        history_emitter = (
            HistoryEventEmitter(
                bus=resolved_history_bus,
                enabled=settings.history_ingest_enabled,
            )
            if resolved_history_bus is not None
            else None
        )
        app.state.history_emitter = history_emitter

        app.state.worker = WorkerService(
            settings=settings,
            repository=app.state.repository,
            bifrost_client=app.state.bifrost_client,
            live_event_bus=app.state.live_event_bus,
            mcp_tool_catalog=app.state.mcp_tool_catalog,
            skill_registry=app.state.skill_registry,
            history_emitter=history_emitter,
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
            if created_valkey_conn is not None:
                await created_valkey_conn.aclose()
            if created_live_event_bus is not None:
                await created_live_event_bus.aclose()
            if created_history_event_bus is not None:
                await created_history_event_bus.aclose()
            if created_engine is not None:
                await created_engine.dispose()
            shutdown_telemetry()

    app = FastAPI(
        title="Agent Orchestrator",
        version="0.1.0",
        description="Background-job harness for LLM-driven DragnCards agents.",
        lifespan=lifespan,
    )
    # Expose settings before lifespan startup so callers (and tests) can read
    # the resolved configuration without entering the lifespan context.
    app.state.settings = settings
    instrument_fastapi_app(app)
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=settings.max_request_body_bytes,
    )
    # Strict CORS allowlist (configurable), matching eval-service. The dashboard
    # reaches the orchestrator through its own server-side proxy rather than from
    # the browser — including the SSE job streams, which are EventSource calls to
    # relative /api/proxy/orchestrator/... URLs — so the allowlist does not break
    # normal dashboard use, and a request carrying no ``Origin`` at all (every
    # server-to-server caller, including that proxy) is outside CORS entirely.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(meta.router)
    app.include_router(catalog.router)
    app.include_router(sessions.router)
    app.include_router(personas.router)
    app.include_router(players.router)
    app.include_router(jobs.router)
    app.include_router(context.router)

    return app
