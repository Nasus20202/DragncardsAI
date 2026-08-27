from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import AgentSession, SessionPlayerConfig


class PlayerConfigRepositoryMixin:
    """Persistence for per-seat player agent configuration.

    One row per seat on the orchestrating session. Nullable columns carry
    "inherit from the session" semantics, so they are written through verbatim
    rather than being defaulted here — resolution happens at spawn time.
    """

    async def upsert_player_config(
        self,
        session_id: str,
        player_id: str,
        *,
        display_name: str | None,
        provider_id: str | None,
        model_name: str | None,
        gateway_options: dict[str, Any] | None,
        provider_options: dict[str, Any] | None,
        skills: list[str] | None,
        persona: str | None = None,
    ) -> SessionPlayerConfig | None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            item = await session.get(SessionPlayerConfig, (session_id, player_id))
            if item is None:
                item = SessionPlayerConfig(
                    session_id=session_id,
                    player_id=player_id,
                )
                session.add(item)
            item.display_name = display_name
            item.provider_id = provider_id
            item.model_name = model_name
            item.gateway_options = gateway_options or {}
            item.provider_options = provider_options or {}
            item.skills_json = None if skills is None else list(skills)
            item.persona = persona
            item.updated_at = utc_now()
        return await self.get_player_config(session_id, player_id)

    async def list_player_configs(self, session_id: str) -> list[SessionPlayerConfig]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SessionPlayerConfig)
                .where(SessionPlayerConfig.session_id == session_id)
                .order_by(SessionPlayerConfig.player_id)
            )
            return list(result.scalars().unique())

    async def get_player_config(
        self, session_id: str, player_id: str
    ) -> SessionPlayerConfig | None:
        async with self._session_factory() as session:
            return await session.get(SessionPlayerConfig, (session_id, player_id))

    async def set_player_agent_session(
        self, session_id: str, player_id: str, agent_session_id: str
    ) -> bool:
        """Record the persistent session a seat now owns.

        Written exactly once per seat per game, when the seat is first prompted.
        The write is conditional on the seat still having no session, so two
        concurrent first prompts for the same seat cannot each install their own —
        the loser is told ``False`` and its caller reuses the winner's session.
        """
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                update(SessionPlayerConfig)
                .where(
                    SessionPlayerConfig.session_id == session_id,
                    SessionPlayerConfig.player_id == player_id,
                    SessionPlayerConfig.agent_session_id.is_(None),
                )
                .values(
                    agent_session_id=agent_session_id,
                    updated_at=utc_now(),
                )
            )
            return result.rowcount == 1

    async def delete_player_config(self, session_id: str, player_id: str) -> bool:
        async with self._session_factory() as session, session.begin():
            item = await session.get(SessionPlayerConfig, (session_id, player_id))
            if item is None:
                return False
            await session.delete(item)
            return True
