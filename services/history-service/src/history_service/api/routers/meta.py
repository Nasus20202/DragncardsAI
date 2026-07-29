from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from history_service.api.deps import get_repository, get_settings
from history_service.config import Settings
from history_service.storage.db import ping_database
from history_service.storage.repository import Repository

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
        "valkey": False,
        "ingester": bool(getattr(request.app.state, "ingester_running", False)),
    }
    if hasattr(repo, "_session_factory"):
        try:
            await ping_database(repo._session_factory)
            ready_state["database"] = True
        except Exception:
            ready_state["database"] = False
    valkey = getattr(request.app.state, "valkey", None)
    if valkey is not None:
        try:
            pong = await valkey.execute("PING")
            ready_state["valkey"] = pong in ("PONG", "pong", True)
        except Exception:
            ready_state["valkey"] = False
    ready_flag = ready_state["database"] and ready_state["valkey"]
    return {
        "status": "ready" if ready_flag else "not_ready",
        "checks": ready_state,
        "http_port": settings.http_port,
    }
