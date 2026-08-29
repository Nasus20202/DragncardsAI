"""Per-seat player agent configuration for orchestrated multi-player games.

Each seat on an orchestrating session gets its own provider, model, reasoning
effort, and skill list, so two configurations can play the same cooperative game
and be compared move-for-move afterwards. Unset fields inherit from the session.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from agent_orchestrator.api.reasoning import validate_reasoning_effort
from agent_orchestrator.api.deps import (
    get_repository,
    get_settings,
    get_skill_registry,
)
from agent_orchestrator.api.serializers import serialize_player_config
from agent_orchestrator.api.skill_assignment import validate_and_register_skills
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


@router.get("/sessions/{session_id}/players", operation_id="list_session_players")
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


@router.put(
    "/sessions/{session_id}/players/{player_id}", operation_id="save_session_player"
)
async def set_player_config(
    session_id: str,
    player_id: str,
    body: PlayerConfigRequest,
    request: Request,
    repo: Repository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
    registry: SkillRegistry = Depends(get_skill_registry),
) -> dict[str, PlayerConfigResponse]:
    if not is_valid_player_id(player_id):
        raise HTTPException(
            status_code=400,
            detail="player_id must be one of player1, player2, player3, player4",
        )
    session = await repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    effective_provider_id = body.provider_id or (
        session.model_config.provider_id if session.model_config is not None else None
    )
    effective_model_name = body.model_name or (
        session.model_config.model_name if session.model_config is not None else None
    )
    if body.provider_id is not None and body.provider_id not in (
        settings.enabled_provider_ids
    ):
        raise HTTPException(status_code=400, detail="Unsupported provider")
    if body.persona is not None:
        # Validated here so an unknown persona is reported to whoever is setting up
        # the table, not to the orchestrator agent in the middle of a game.
        if await repo.get_persona(body.persona) is None:
            raise HTTPException(
                status_code=400, detail=f"Unknown persona: {body.persona}"
            )
    if body.skills is not None:
        if len(body.skills) > MAX_PLAYER_SKILLS:
            raise HTTPException(
                status_code=400,
                detail=f"At most {MAX_PLAYER_SKILLS} skills may be assigned to a player",
            )
        await validate_and_register_skills(body.skills, registry=registry, repo=repo)

    gateway_options = dict(body.gateway_options)
    if body.reasoning is not None:
        if body.reasoning.enabled:
            await validate_reasoning_effort(
                request.app.state.bifrost_client,
                provider_id=effective_provider_id,
                model_name=effective_model_name,
                effort=body.reasoning.effort,
            )
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
        persona=body.persona,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"player": serialize_player_config(item)}


@router.delete(
    "/sessions/{session_id}/players/{player_id}",
    status_code=204,
    operation_id="delete_session_player",
)
async def delete_player_config(
    session_id: str,
    player_id: str,
    repo: Repository = Depends(get_repository),
) -> None:
    existing = await repo.get_player_config(session_id, player_id)
    if existing is not None and existing.agent_session_id:
        # The seat's own session is terminated with the seat, so removing a player
        # from the table does not leave its agent session running.
        await repo.terminate_session(existing.agent_session_id)
    removed = await repo.delete_player_config(session_id, player_id)
    if not removed:
        raise HTTPException(
            status_code=404, detail="Player not configured for this session"
        )
