from __future__ import annotations

from fastapi import APIRouter, Depends

from eval_service.api.deps import (
    get_history_client,
    get_judge_client,
    get_repository,
    get_settings,
)
from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostJudgeClient
from eval_service.integrations.history import HistoryClient
from eval_service.storage.repository import Repository

router = APIRouter(tags=["meta"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def ready(
    repo: Repository = Depends(get_repository),
    history: HistoryClient = Depends(get_history_client),
    judge: BifrostJudgeClient = Depends(get_judge_client),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    checks = {"database": False, "history": False, "bifrost": False}

    try:
        await repo.ping()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    try:
        checks["history"] = await history.health()
    except Exception:
        checks["history"] = False

    try:
        checks["bifrost"] = await judge.health()
    except Exception:
        checks["bifrost"] = False

    # The judge model must be configured for the service to be able to evaluate;
    # report it (never the key itself) so readiness reflects evaluability.
    judge_configured = settings.judge_configured
    all_ok = all(checks.values()) and judge_configured
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "judge_configured": judge_configured,
    }
