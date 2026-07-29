from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agent_orchestrator.api.deps import get_repository, get_settings
from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.live_event_resilience import unwrap_live_event_bus
from agent_orchestrator.runtime.live_events import (
    InMemoryLiveEventBus,
    ValkeyLiveEventBus,
)
from agent_orchestrator.storage.db import ping_database
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["meta"])


@router.get("/health", operation_id="health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", operation_id="ready")
async def ready(
    request: Request,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    ready_state = {
        "database": False,
        "bifrost": False,
        "valkey": False,
        "worker": bool(request.app.state.worker.is_running),
    }
    if hasattr(repo, "_session_factory"):
        try:
            await ping_database(repo._session_factory)
            ready_state["database"] = True
        except Exception:
            ready_state["database"] = False
    try:
        ready_state["bifrost"] = await request.app.state.bifrost_client.health()
    except Exception:
        ready_state["bifrost"] = False
    try:
        # Unwrapped first: the app hands every consumer a best-effort wrapper
        # around the real bus, and readiness is asking which concrete bus is
        # configured, not whether it is wrapped.
        ready_state["valkey"] = isinstance(
            unwrap_live_event_bus(request.app.state.live_event_bus),
            (ValkeyLiveEventBus, InMemoryLiveEventBus),
        )
    except Exception:
        ready_state["valkey"] = False
    ready_flag = all(ready_state.values())
    return {
        "status": "ready" if ready_flag else "not_ready",
        "checks": ready_state,
        "http_port": settings.http_port,
    }
