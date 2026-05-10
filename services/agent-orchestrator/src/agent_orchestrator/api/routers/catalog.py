from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from agent_orchestrator.api.deps import get_settings, get_skill_registry
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostError
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.catalog import ProviderResponse, SkillDefinitionResponse

router = APIRouter(tags=["catalog"])


def _matches_provider_model(provider_id: str, model_id: str, model_prefix: str) -> bool:
    if model_id.startswith(f"{model_prefix}/"):
        return True
    if "/" in model_id:
        return False
    if provider_id == "openai":
        return True
    return model_id.startswith(provider_id) or model_id.startswith(model_prefix)


@router.get("/providers")
async def list_providers(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, list[ProviderResponse]]:
    providers: list[ProviderResponse] = []
    bifrost_client = request.app.state.bifrost_client
    for provider_id in settings.enabled_provider_ids:
        model_prefix = settings.provider_prefixes[provider_id]
        try:
            model_infos = await bifrost_client.list_models(provider_id)
            models = [
                model.id
                for model in model_infos
                if _matches_provider_model(provider_id, model.id, model_prefix)
            ]
            available = True
            error = None
        except BifrostError as exc:
            models = []
            available = False
            error = str(exc)
        except Exception:
            models = []
            available = False
            error = "Failed to list models"
        providers.append(
            ProviderResponse(
                provider_id=provider_id,
                model_prefix=model_prefix,
                models=models,
                available=available,
                error=error,
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
            content_markdown=registry.load_markdown(definition.name),
        )
        for definition in registry.list_skills().values()
    ]
    skills.sort(key=lambda item: item.name)
    return {"skills": skills}
