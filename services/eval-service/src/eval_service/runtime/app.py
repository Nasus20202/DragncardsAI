from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from eval_service.api.routers import evaluations, meta
from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostJudgeClient
from eval_service.integrations.history import HistoryClient
from eval_service.judge.config import SkillResolver
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.inflight import InflightRegistry
from eval_service.runtime.live_events import LiveEventBus
from eval_service.runtime.requests import RequestService
from eval_service.runtime.rounds import RoundsService
from eval_service.runtime.stream import EvaluationStreamService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schema_migrations import ensure_schema
from eval_service.storage.db import create_engine, create_session_factory
from eval_service.storage.repository import Repository
from eval_service.telemetry import instrument_fastapi_app, shutdown_telemetry

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: Settings | None = None,
    repository: Repository | None = None,
    history_client: HistoryClient | None = None,
    judge_client: BifrostJudgeClient | None = None,
    start_worker: bool = True,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        created_engine = None
        created_history = None
        created_judge = None
        worker_task = None

        if repository is None:
            logger.info(
                "Initializing repository with database %s",
                settings.eval_database_url,
            )
            created_engine = create_engine(settings.eval_database_url)
            await ensure_schema(created_engine)
            app.state.repository = Repository(create_session_factory(created_engine))
        else:
            app.state.repository = repository

        app.state.history_client = history_client or HistoryClient(
            settings.history_service_base_url, page_size=settings.history_page_size
        )
        if history_client is None:
            created_history = app.state.history_client

        app.state.judge_client = judge_client or BifrostJudgeClient(
            settings.bifrost_url,
            settings.bifrost_api_key,
            timeout_seconds=settings.eval_judge_timeout_seconds,
            key_name=settings.eval_judge_bifrost_key_name,
        )
        if judge_client is None:
            created_judge = app.state.judge_client

        # Transient live-push + cancellation bookkeeping (durable state stays in
        # Postgres). Shared by the worker (publisher) and the SSE/cancel routes.
        skill_resolver = SkillResolver(settings.skill_root_paths)
        live_bus = LiveEventBus()
        inflight = InflightRegistry()
        app.state.live_bus = live_bus
        app.state.inflight = inflight
        app.state.skill_resolver = skill_resolver

        app.state.request_service = RequestService(
            settings=settings,
            repository=app.state.repository,
            history=app.state.history_client,
            skill_resolver=skill_resolver,
            inflight=inflight,
        )
        app.state.rounds_service = RoundsService(history=app.state.history_client)
        evaluator = Evaluator(
            settings=settings,
            repository=app.state.repository,
            history=app.state.history_client,
            judge=app.state.judge_client,
            skill_resolver=skill_resolver,
        )
        app.state.evaluator = evaluator
        app.state.settings = settings
        app.state.stream_service = EvaluationStreamService(
            repository=app.state.repository, live_bus=live_bus
        )
        app.state.worker = None

        if start_worker:
            worker = EvaluationWorker(
                settings=settings,
                repository=app.state.repository,
                history=app.state.history_client,
                evaluator=evaluator,
                live_bus=live_bus,
                inflight=inflight,
            )
            app.state.worker = worker
            worker_task = asyncio.create_task(worker.run_forever())
            logger.info("Evaluation worker task started")

        if not settings.judge_configured:
            logger.warning(
                "EVAL_JUDGE_MODEL is not configured; evaluations will be skipped "
                "with a clear error until a judge model is set"
            )

        if not settings.eval_judge_bifrost_key_name.strip():
            logger.warning(
                "EVAL_JUDGE_BIFROST_KEY_NAME is empty: judge calls will draw the "
                "provider's normal game-playing key pool instead of a dedicated "
                "judge key, so judge spend is billed to the game-playing budget"
            )

        try:
            yield
        finally:
            logger.info("Shutting down eval-service")
            if worker_task is not None:
                await app.state.worker.stop()
                worker_task.cancel()
                try:
                    await worker_task
                except asyncio.CancelledError:
                    pass
            if created_history is not None:
                await created_history.aclose()
            if created_judge is not None:
                await created_judge.aclose()
            if created_engine is not None:
                await created_engine.dispose()
            shutdown_telemetry()

    app = FastAPI(
        title="Eval Service",
        version="0.1.0",
        description="On-demand LLM move-evaluation service (the judge).",
        lifespan=lifespan,
    )
    app.state.settings = settings
    instrument_fastapi_app(app)

    # Strict CORS allowlist (configurable). The dashboard reaches eval-service
    # through a server-side proxy, not browser-direct, so the allowlist does not
    # break normal dashboard use.
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
    app.include_router(evaluations.router)

    return app
