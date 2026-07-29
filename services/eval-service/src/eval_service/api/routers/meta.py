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


@router.get("/health", operation_id="health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", operation_id="ready")
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
    judge_key = await _judge_key_status(judge, settings)
    all_ok = (
        all(checks.values()) and judge_configured and judge_key["status"] != "missing"
    )
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "judge_configured": judge_configured,
        "judge_key": judge_key,
    }


async def _judge_key_status(
    judge: BifrostJudgeClient, settings: Settings
) -> dict[str, object]:
    """Whether the judge's dedicated Bifrost key exists for its target provider.

    Reports names only -- never a key value. ``missing`` degrades readiness: the
    judge would otherwise fail every call for that provider. ``unknown`` (the
    gateway's key listing is unreadable) does not degrade on its own, since the
    ``bifrost`` check already covers reachability. ``disabled`` records the
    deliberate opt-out where judge calls draw the game-playing key pool.

    Only the ENV default provider can be checked here; a request may override the
    judge provider, and that case surfaces as an explicit gateway error on the
    target instead.
    """
    key_name = settings.eval_judge_bifrost_key_name.strip()
    provider = settings.judge_routing_provider
    if not key_name:
        return {"name": "", "provider": provider, "status": "disabled"}
    if not provider:
        return {"name": key_name, "provider": "", "status": "unknown"}
    providers = await judge.named_key_providers(key_name)
    if providers is None:
        return {"name": key_name, "provider": provider, "status": "unknown"}
    return {
        "name": key_name,
        "provider": provider,
        "status": "present" if provider in providers else "missing",
        # Which providers CAN judge, so switching provider is an informed choice.
        "providers": sorted(providers),
    }
