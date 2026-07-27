"""Per-seat player agent configuration for orchestrated multi-player games.

Each seat on an orchestrating session gets its own provider, model, reasoning
effort, and skill list, so two configurations can play the same cooperative game
and be compared move-for-move afterwards. Unset fields inherit from the session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent_orchestrator.api.deps import (
    get_repository,
    get_settings,
    get_skill_registry,
)
from agent_orchestrator.api.serializers import serialize_player_config
from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.player_agents import (
    MAX_PLAYER_SKILLS,
    fold_reasoning,
    is_valid_player_id,
)
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.schemas.players import (
    PlayerConfigListResponse,
    PlayerConfigRequest,
    PlayerConfigResponse,
)
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["players"])


@router.get("/sessions/{session_id}/players")
async def list_player_configs(
    session_id: str,
    repo: Repository = Depends(get_repository),
) -> PlayerConfigListResponse:
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    configs = await repo.list_player_configs(session_id)
    return PlayerConfigListResponse(
        players=[serialize_player_config(config) for config in configs]
    )


@router.put("/sessions/{session_id}/players/{player_id}")
async def set_player_config(
    session_id: str,
    player_id: str,
    body: PlayerConfigRequest,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, PlayerConfigResponse]:
    if not is_valid_player_id(player_id):
        raise HTTPException(
            status_code=400,
            detail="player_id must be one of player1, player2, player3, player4",
        )
    if body.provider_id is not None and body.provider_id not in (
        settings.enabled_provider_ids
    ):
        raise HTTPException(status_code=400, detail="Unsupported provider")
    if body.skills is not None:
        if len(body.skills) > MAX_PLAYER_SKILLS:
            raise HTTPException(
                status_code=400,
                detail=f"At most {MAX_PLAYER_SKILLS} skills may be assigned to a player",
            )
        for skill_name in body.skills:
            definition = registry.resolve(skill_name)
            if definition is None:
                raise HTTPException(
                    status_code=400, detail=f"Unknown skill: {skill_name}"
                )
            # Register the skill globally now. A seat's skills are enabled on a
            # child session at spawn time, and enablement requires a registry
            # row — without this a skill only this seat uses would be silently
            # dropped when its player agent starts.
            await repo.add_skill_registry(
                name=skill_name,
                skill_path=str(definition.path),
                description=definition.description,
                metadata_json={},
            )

    gateway_options = dict(body.gateway_options)
    if body.reasoning is not None:
        gateway_options = fold_reasoning(
            gateway_options,
            enabled=body.reasoning.enabled,
            effort=body.reasoning.effort,
            max_tokens=body.reasoning.max_tokens,
        )

    item = await repo.upsert_player_config(
        session_id,
        player_id,
        display_name=body.display_name,
        provider_id=body.provider_id,
        model_name=body.model_name,
        gateway_options=gateway_options,
        provider_options=body.provider_options,
        skills=body.skills,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"player": serialize_player_config(item)}


@router.delete("/sessions/{session_id}/players/{player_id}", status_code=204)
async def delete_player_config(
    session_id: str,
    player_id: str,
    repo: Repository = Depends(get_repository),
) -> None:
    removed = await repo.delete_player_config(session_id, player_id)
    if not removed:
        raise HTTPException(
            status_code=404, detail="Player not configured for this session"
        )
