from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Request

from agent_orchestrator.api.deps import get_settings, get_skill_registry
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostError
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.catalog import ProviderResponse, SkillDefinitionResponse

router = APIRouter(tags=["catalog"])


async def _build_provider_response(
    *,
    bifrost_client,
    provider_id: str,
    model_prefix: str,
) -> ProviderResponse:
    try:
        model_infos = await bifrost_client.list_models(provider_id)
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
    settings: Settings = Depends(get_settings),
) -> dict[str, list[ProviderResponse]]:
    bifrost_client = request.app.state.bifrost_client
    provider_ids = tuple(dict.fromkeys(settings.enabled_provider_ids))
    providers = await asyncio.gather(
        *(
            _build_provider_response(
                bifrost_client=bifrost_client,
                provider_id=provider_id,
                model_prefix=settings.provider_prefixes[provider_id],
            )
            for provider_id in provider_ids
        )
    )
    return {"providers": providers}


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
