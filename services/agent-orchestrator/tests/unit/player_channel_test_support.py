"""Fixtures for the two seat channels: a table, a seat's session, an invocation.

``invoke_seat`` runs a seat's job through the real :class:`PromptRunService` and
returns the messages the model was actually sent. Delivery and finding-carrying
happen during message assembly, so nothing short of running the assembly proves
they happened — and asserting on the message list is what catches a change that
moves player text into the system prompt.
"""

from __future__ import annotations

from typing import Any

from agent_orchestrator.config import Settings
from agent_orchestrator.integrations.bifrost import ChatResponse
from agent_orchestrator.integrations.mcp.tools import McpToolCatalog
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
    SeatIdentity,
    resolve_seat_identity,
)
from agent_orchestrator.runtime.prompt_run import (
    PromptRunDependencies,
    PromptRunService,
)
from agent_orchestrator.runtime.session_modes import SESSION_MODE_ORCHESTRATED
from agent_orchestrator.runtime.session_transcript import SessionTranscriptService
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.models import AgentSession
from agent_orchestrator.storage.repository import Repository


class RecordingBifrost:
    """A gateway that answers immediately and keeps every message list it saw."""

    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get_model_context_length(self, provider_id, model_name) -> int | None:
        return None

    async def chat_completion(
        self,
        provider_id,
        model_name,
        messages,
        tools,
        gateway_options,
        provider_options,
        on_delta=None,
    ) -> ChatResponse:
        self.calls.append([dict(message) for message in messages])
        return ChatResponse(content="turn taken", tool_calls=[], raw={})


class SilentMcp:
    async def list_tools(self, server_url, transport, headers=None):
        return []

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        return {"is_error": False, "content": [{"type": "text", "text": "done"}]}


async def table(
    repo: Repository,
    *,
    mode: str = SESSION_MODE_ORCHESTRATED,
    seats: tuple[str, ...] = ("player1", "player2"),
) -> AgentSession:
    """An orchestrating session with the named seats configured."""
    session = await repo.create_session("table", {}, session_mode=mode)
    await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="parent-model",
        gateway_options={},
        provider_options={},
    )
    for player_id in seats:
        await repo.upsert_player_config(
            session.id,
            player_id,
            display_name=None,
            provider_id="openai",
            model_name="seat-model",
            gateway_options={},
            provider_options={},
            skills=[],
            persona=None,
        )
    loaded = await repo.get_session(session.id)
    assert loaded is not None
    return loaded


async def seat_session(
    repo: Repository, orchestrator_session_id: str, player_id: str
) -> AgentSession:
    """The seat's own persistent session, tagged the way the orchestrator tags it.

    The metadata written here is exactly what ``prompt_player_agent`` writes, and
    it is the authority on which seat a job is: no tool a player holds can change
    session metadata.
    """
    child = await repo.create_session(
        player_id,
        {
            SESSION_PLAYER_ID_KEY: player_id,
            SESSION_ORCHESTRATOR_ID_KEY: orchestrator_session_id,
        },
        multi_turn_memory=True,
    )
    await repo.set_model_config(
        child.id,
        provider_id="openai",
        model_name="seat-model",
        gateway_options={},
        provider_options={},
    )
    await repo.set_player_agent_session(orchestrator_session_id, player_id, child.id)
    loaded = await repo.get_session(child.id)
    assert loaded is not None
    return loaded


async def seat_identity_for(
    repo: Repository, orchestrator_session_id: str, player_id: str
) -> SeatIdentity:
    """The resolved seat identity for a seat whose session already exists."""
    seat = await repo.get_player_config(orchestrator_session_id, player_id)
    assert seat is not None and seat.agent_session_id is not None
    child = await repo.get_session(seat.agent_session_id)
    identity = await resolve_seat_identity(child, load_session=repo.get_session)
    assert identity is not None
    return identity


async def invoke_seat(
    repo: Repository,
    skills: SkillRegistry,
    seat: AgentSession,
    *,
    prompt: str,
) -> list[dict[str, Any]]:
    """Run one job on a seat's session and return the messages the model got."""
    job = await repo.enqueue_prompt_job(
        seat.id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    assert job is not None
    claimed = await repo.claim_next_job()
    assert claimed is not None

    bifrost = RecordingBifrost()
    service = PromptRunService(
        dependencies=PromptRunDependencies(
            settings=Settings(SKILL_ROOTS=str(skills._roots[0])),
            repository=repo,
            bifrost_client=bifrost,
            live_event_bus=InMemoryLiveEventBus(),
            mcp_tool_catalog=McpToolCatalog(SilentMcp()),
            skill_registry=skills,
        ),
        transcript_service=SessionTranscriptService(repo),
        schedule_child_job=lambda job_id: None,
    )
    await service.run(claimed)

    stored = await repo.get_job(job.id)
    assert stored is not None, "the seat's job vanished mid-run"
    assert stored.status == "completed", stored.error_message
    assert bifrost.calls, "the gateway was never called, so nothing was assembled"
    return bifrost.calls[0]
