"""Deployment-global agent personas.

A persona bundles a detailed system prompt, a skill selection, and a tool
configuration under a name, so the same agent character can be authored once and
reused across sessions and games. `PUT` upserts, matching how the skill and MCP
registries this table sits beside are written.

Personas are global rather than per-user because the service carries no user
identity to scope them to, and global rather than per-session because outliving
one session is the whole reason a persona exists instead of a per-seat row.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent_orchestrator.api.deps import (
    get_repository,
    get_settings,
    get_skill_registry,
)
from agent_orchestrator.api.serializers import serialize_persona
from agent_orchestrator.api.skill_assignment import validate_and_register_skills
from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.personas import is_valid_persona_name
from agent_orchestrator.runtime.player_agents import fold_reasoning
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.personas import (
    PersonaListResponse,
    PersonaRequest,
    PersonaResponse,
)
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["personas"])


@router.get("/personas")
async def list_personas(
    repo: Repository = Depends(get_repository),
) -> PersonaListResponse:
    personas = await repo.list_personas()
    return PersonaListResponse(personas=[serialize_persona(item) for item in personas])


@router.get("/personas/{name}")
async def get_persona(
    name: str,
    repo: Repository = Depends(get_repository),
) -> dict[str, PersonaResponse]:
    item = await repo.get_persona(name)
    if item is None:
        raise HTTPException(status_code=404, detail="Persona not found")
    return {"persona": serialize_persona(item)}


@router.put("/personas/{name}")
async def set_persona(
    name: str,
    body: PersonaRequest,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, PersonaResponse]:
    if not is_valid_persona_name(name):
        raise HTTPException(
            status_code=400,
            detail=(
                "Persona name must be a lowercase slug of letters, digits and "
                "hyphens, starting with a letter or digit, at most 64 characters"
            ),
        )
    if body.provider_id is not None and body.provider_id not in (
        settings.enabled_provider_ids
    ):
        raise HTTPException(status_code=400, detail="Unsupported provider")
    if body.skills is not None:
        await validate_and_register_skills(body.skills, registry=registry, repo=repo)

    gateway_options = dict(body.gateway_options)
    if body.reasoning is not None:
        gateway_options = fold_reasoning(
            gateway_options,
            enabled=body.reasoning.enabled,
            effort=body.reasoning.effort,
            max_tokens=body.reasoning.max_tokens,
        )

    item = await repo.upsert_persona(
        name,
        display_name=body.display_name,
        description=body.description,
        system_prompt=body.system_prompt,
        provider_id=body.provider_id,
        model_name=body.model_name,
        gateway_options=gateway_options,
        provider_options=body.provider_options,
        skills=body.skills,
        allowed_tools=body.allowed_tools,
    )
    return {"persona": serialize_persona(item)}


@router.delete("/personas/{name}", status_code=204)
async def delete_persona(
    name: str,
    repo: Repository = Depends(get_repository),
) -> None:
    """Delete a persona.

    Unconditional by design: a subagent started from a persona captured its
    configuration at start time, so nothing running depends on this row. Any
    session naming it as a default has that default cleared.
    """
    removed = await repo.delete_persona(name)
    if not removed:
        raise HTTPException(status_code=404, detail="Persona not found")
