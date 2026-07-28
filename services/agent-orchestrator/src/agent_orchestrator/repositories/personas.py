from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import AgentPersona, AgentSession


class PersonaRepositoryMixin:
    """Persistence for deployment-global agent personas.

    Keyed by name, and written through verbatim: a persona's nullable columns
    carry "inherit" / "do not narrow" meaning that only resolution at spawn time
    may interpret, so nothing is defaulted here.
    """

    async def upsert_persona(
        self,
        name: str,
        *,
        display_name: str | None,
        description: str | None,
        system_prompt: str,
        provider_id: str | None,
        model_name: str | None,
        gateway_options: dict[str, Any] | None,
        provider_options: dict[str, Any] | None,
        skills: list[str] | None,
        allowed_tools: list[str] | None,
    ) -> AgentPersona:
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentPersona, name)
            if item is None:
                item = AgentPersona(name=name)
                session.add(item)
            item.display_name = display_name
            item.description = description
            item.system_prompt = system_prompt
            item.provider_id = provider_id
            item.model_name = model_name
            item.gateway_options = gateway_options or {}
            item.provider_options = provider_options or {}
            item.skills_json = None if skills is None else list(skills)
            item.allowed_tools_json = (
                None if allowed_tools is None else list(allowed_tools)
            )
            item.updated_at = utc_now()
        loaded = await self.get_persona(name)
        assert loaded is not None
        return loaded

    async def list_personas(self) -> list[AgentPersona]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentPersona).order_by(AgentPersona.name)
            )
            return list(result.scalars().unique())

    async def get_persona(self, name: str) -> AgentPersona | None:
        async with self._session_factory() as session:
            return await session.get(AgentPersona, name)

    async def delete_persona(self, name: str) -> bool:
        """Delete a persona, clearing it from any session that defaults to it.

        Deletion is unconditional — no reference counting and no soft delete —
        because a subagent started from a persona captured its configuration at
        start time and never re-reads this row. The only live reference is a
        session's default, which is cleared in the same transaction so no session
        is left naming a persona that is gone.
        """
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentPersona, name)
            if item is None:
                return False
            await session.execute(
                update(AgentSession)
                .where(AgentSession.default_subagent_persona == name)
                .values(default_subagent_persona=None)
            )
            await session.delete(item)
            return True
