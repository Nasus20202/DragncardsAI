from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request

from agent_orchestrator.api.deps import get_settings, get_skill_registry
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostError
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.catalog import (
    ProviderCacheRefreshResponse,
    ProviderResponse,
    SkillDefinitionResponse,
)

router = APIRouter(tags=["catalog"])


# Hard upper bound (seconds) added on top of the per-provider list-models timeout.
# The BifrostClient already enforces a short per-request httpx timeout for model
# listing; this guard is a defensive ceiling so a single provider can never stall
# the aggregate /providers response, regardless of the client implementation.
_LIST_MODELS_GUARD_MARGIN_SECONDS = 2.0


async def _build_provider_response(
    *,
    bifrost_client,
    provider_id: str,
    model_prefix: str,
    timeout_seconds: float,
) -> ProviderResponse:
    try:
        model_infos = await asyncio.wait_for(
            bifrost_client.list_models(provider_id),
            timeout=timeout_seconds,
        )
        models = [
            model.id for model in model_infos if model.id.startswith(f"{model_prefix}/")
        ]
        return ProviderResponse(
            provider_id=provider_id,
            model_prefix=model_prefix,
            models=models,
            available=True,
            error=None,
        )
    except TimeoutError:
        # asyncio.TimeoutError is an alias of the builtin TimeoutError on 3.11+.
        return ProviderResponse(
            provider_id=provider_id,
            model_prefix=model_prefix,
            models=[],
            available=False,
            error="Timed out while listing models",
        )
    except BifrostError as exc:
        return ProviderResponse(
            provider_id=provider_id,
            model_prefix=model_prefix,
            models=[],
            available=False,
            error=str(exc),
        )
    except Exception:
        return ProviderResponse(
            provider_id=provider_id,
            model_prefix=model_prefix,
            models=[],
            available=False,
            error="Failed to list models",
        )


@router.get("/providers")
async def list_providers(
    request: Request,
    refresh: bool = False,
    settings: Settings = Depends(get_settings),
) -> dict[str, list[ProviderResponse]]:
    bifrost_client = request.app.state.bifrost_client
    provider_ids = tuple(dict.fromkeys(settings.enabled_provider_ids))
    # `?refresh=true` forces a single uncached re-probe by clearing the positive
    # and negative model-cache entries before listing.
    if refresh:
        await bifrost_client.clear_model_cache(list(provider_ids))
    timeout_seconds = (
        settings.bifrost_list_models_timeout_seconds + _LIST_MODELS_GUARD_MARGIN_SECONDS
    )
    providers = await asyncio.gather(
        *(
            _build_provider_response(
                bifrost_client=bifrost_client,
                provider_id=provider_id,
                model_prefix=settings.provider_prefixes[provider_id],
                timeout_seconds=timeout_seconds,
            )
            for provider_id in provider_ids
        )
    )
    return {"providers": providers}


@router.post("/providers/refresh")
async def refresh_provider_cache(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> ProviderCacheRefreshResponse:
    """Flush cached provider model listings (positive and negative entries).

    Lets an operator force a re-probe after adding an API key so a previously
    unavailable provider is listed again on the next `/providers` call without
    waiting for the negative-cache TTL to expire.
    """
    bifrost_client = request.app.state.bifrost_client
    provider_ids = list(dict.fromkeys(settings.enabled_provider_ids))
    summary = await bifrost_client.clear_model_cache(provider_ids)
    return ProviderCacheRefreshResponse(
        status="cleared",
        providers=summary["providers"],
        keys_cleared=summary["keys_cleared"],
    )


@router.get("/skills")
async def list_available_skills(
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, list[SkillDefinitionResponse]]:
    skills = [
        SkillDefinitionResponse(
            name=definition.name,
            path=str(definition.path),
            description=definition.description,
            metadata=definition.metadata,
        )
        for definition in registry.list_skills().values()
    ]
    skills.sort(key=lambda item: item.name)
    return {"skills": skills}
