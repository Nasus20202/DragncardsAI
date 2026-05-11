"""Context management endpoints: manual compaction and context metadata."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agent_orchestrator.api.deps import (
    get_bifrost_client,
    get_repository,
    get_settings,
    require_session,
)
from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import BifrostClient
from agent_orchestrator.runtime.compaction import perform_compaction
from agent_orchestrator.schemas.context import ContextMetadataResponse
from agent_orchestrator.storage.models import AgentSession
from agent_orchestrator.storage.repository import Repository

router = APIRouter(tags=["context"])


async def _resolve_context_window(
    session: AgentSession, settings: Settings, bifrost_client: BifrostClient
) -> int:
    if session.model_config:
        context_length = await bifrost_client.get_model_context_length(
            session.model_config.provider_id, session.model_config.model_name
        )
        if context_length:
            return context_length
    return settings.context_window_size


@router.post("/sessions/{session_id}/compact")
async def compact_session(
    session_id: str,
    session: AgentSession = Depends(require_session),
    repo: Repository = Depends(get_repository),
    bifrost_client: BifrostClient = Depends(get_bifrost_client),
    settings: Settings = Depends(get_settings),
) -> ContextMetadataResponse:
    """Trigger manual compaction for a session.

    Returns 409 if multi_turn_memory is disabled on the session.
    """
    if not session.multi_turn_memory:
        raise HTTPException(
            status_code=409,
            detail="Compaction requires multi_turn_memory to be enabled on this session",
        )

    model_config = session.model_config
    if model_config is None:
        raise HTTPException(
            status_code=422, detail="Session has no model configuration"
        )

    try:
        await perform_compaction(
            repository=repo,
            bifrost_client=bifrost_client,
            session_id=session_id,
            model_config=model_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    context_window_size = await _resolve_context_window(
        session, settings, bifrost_client
    )
    metadata = await repo.get_context_metadata(session_id, context_window_size)
    return ContextMetadataResponse(**metadata)


@router.get("/sessions/{session_id}/context")
async def get_context_metadata(
    session_id: str,
    session: AgentSession = Depends(require_session),
    repo: Repository = Depends(get_repository),
    bifrost_client: BifrostClient = Depends(get_bifrost_client),
    settings: Settings = Depends(get_settings),
) -> ContextMetadataResponse:
    """Return current context health metadata for a session."""
    context_window_size = await _resolve_context_window(
        session, settings, bifrost_client
    )
    metadata = await repo.get_context_metadata(session_id, context_window_size)
    return ContextMetadataResponse(**metadata)
