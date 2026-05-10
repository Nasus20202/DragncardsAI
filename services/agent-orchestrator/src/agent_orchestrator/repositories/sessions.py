from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import (
    AgentSession,
    SessionMcpAssignment,
    SessionModelConfig,
    SessionSkillAssignment,
)


class SessionRepositoryMixin:
    async def create_session(self, name: str | None, metadata_json: dict[str, Any] | None) -> AgentSession:
        async with self._session_factory() as session, session.begin():
            item = AgentSession(name=name, metadata_json=metadata_json or {})
            session.add(item)
            await session.flush()
            session_id = item.id
        loaded = await self.get_session(session_id)
        assert loaded is not None
        return loaded

    async def list_sessions(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentSession], int]:
        async with self._session_factory() as session:
            query = self._session_query()
            count_query = select(func.count()).select_from(AgentSession)
            if status is not None:
                query = query.where(AgentSession.status == status)
                count_query = count_query.where(AgentSession.status == status)
            total = await session.scalar(count_query)
            result = await session.execute(
                query.order_by(AgentSession.created_at.desc()).offset(offset).limit(limit)
            )
            return list(result.scalars().unique()), int(total or 0)

    async def get_session(self, session_id: str) -> AgentSession | None:
        async with self._session_factory() as session:
            result = await session.execute(self._session_query().where(AgentSession.id == session_id))
            return result.scalars().unique().first()

    async def update_session(
        self,
        session_id: str,
        *,
        name: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> AgentSession | None:
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentSession, session_id)
            if item is None:
                return None
            if name is not None:
                item.name = name
            if metadata_json is not None:
                item.metadata_json = metadata_json
            item.updated_at = utc_now()
        return await self.get_session(session_id)

    async def terminate_session(self, session_id: str) -> AgentSession | None:
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentSession, session_id)
            if item is None:
                return None
            item.status = "terminated"
            item.terminated_at = utc_now()
            item.updated_at = utc_now()
        return await self.get_session(session_id)

    async def set_model_config(
        self,
        session_id: str,
        *,
        provider_id: str,
        model_name: str,
        gateway_options: dict[str, Any] | None,
        provider_options: dict[str, Any] | None,
    ) -> SessionModelConfig | None:
        async with self._session_factory() as session, session.begin():
            session_obj = await session.get(AgentSession, session_id)
            if session_obj is None:
                return None
            config = await session.get(SessionModelConfig, session_id)
            if config is None:
                config = SessionModelConfig(session_id=session_id, provider_id=provider_id, model_name=model_name)
                session.add(config)
            config.provider_id = provider_id
            config.model_name = model_name
            config.gateway_options = gateway_options or {}
            config.provider_options = provider_options or {}
            config.updated_at = utc_now()
        session_obj = await self.get_session(session_id)
        return None if session_obj is None else session_obj.model_config

    async def add_skill_assignment(self, session_id: str, skill_name: str, skill_path: str) -> SessionSkillAssignment | None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            result = await session.execute(
                select(SessionSkillAssignment).where(
                    SessionSkillAssignment.session_id == session_id,
                    SessionSkillAssignment.skill_name == skill_name,
                )
            )
            item = result.scalars().first()
            if item is None:
                item = SessionSkillAssignment(
                    session_id=session_id,
                    skill_name=skill_name,
                    skill_path=skill_path,
                )
                session.add(item)
            else:
                item.skill_path = skill_path
            await session.flush()
            item_id = item.id
        return await self.get_skill_assignment(item_id)

    async def get_skill_assignment(self, assignment_id: str) -> SessionSkillAssignment | None:
        async with self._session_factory() as session:
            return await session.get(SessionSkillAssignment, assignment_id)

    async def remove_skill_assignment(self, session_id: str, skill_name: str) -> bool:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(SessionSkillAssignment).where(
                    SessionSkillAssignment.session_id == session_id,
                    SessionSkillAssignment.skill_name == skill_name,
                )
            )
            item = result.scalars().first()
            if item is None:
                return False
            await session.delete(item)
            return True

    async def add_mcp_assignment(
        self,
        session_id: str,
        *,
        name: str,
        transport: str,
        server_url: str,
        headers_json: dict[str, Any] | None,
    ) -> SessionMcpAssignment | None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            result = await session.execute(
                select(SessionMcpAssignment).where(
                    SessionMcpAssignment.session_id == session_id,
                    SessionMcpAssignment.name == name,
                )
            )
            item = result.scalars().first()
            if item is None:
                item = SessionMcpAssignment(
                    session_id=session_id,
                    name=name,
                    transport=transport,
                    server_url=server_url,
                    headers_json=headers_json or {},
                )
                session.add(item)
            else:
                item.transport = transport
                item.server_url = server_url
                item.headers_json = headers_json or {}
                item.updated_at = utc_now()
            await session.flush()
            item_id = item.id
        return await self.get_mcp_assignment(item_id)

    async def get_mcp_assignment(self, assignment_id: str) -> SessionMcpAssignment | None:
        async with self._session_factory() as session:
            return await session.get(SessionMcpAssignment, assignment_id)

    async def remove_mcp_assignment(self, session_id: str, assignment_name: str) -> bool:
        async with self._session_factory() as session, session.begin():
            result = await session.execute(
                select(SessionMcpAssignment).where(
                    SessionMcpAssignment.session_id == session_id,
                    SessionMcpAssignment.name == assignment_name,
                )
            )
            item = result.scalars().first()
            if item is None:
                return False
            await session.delete(item)
            return True
