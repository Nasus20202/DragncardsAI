from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.storage.models import (
    AgentSession,
    Job,
    McpRegistry,
    SessionEnabledMcp,
    SessionModelConfig,
    SessionEnabledSkill,
    SkillRegistry,
)


class SessionRepositoryMixin:
    async def ensure_session_default_mcps(self, session_id: str) -> None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return

            registries_result = await session.execute(
                select(McpRegistry).where(McpRegistry.custom.is_(False))
            )
            registries = list(registries_result.scalars().unique())
            if not registries:
                return

            enabled_result = await session.execute(
                select(SessionEnabledMcp.mcp_name).where(
                    SessionEnabledMcp.session_id == session_id
                )
            )
            enabled_names = set(enabled_result.scalars())

            for registry in registries:
                if registry.name in enabled_names:
                    continue
                session.add(
                    SessionEnabledMcp(
                        session_id=session_id,
                        mcp_name=registry.name,
                        enabled=True,
                    )
                )

    @staticmethod
    def _top_level_session_filter():
        return ~AgentSession.jobs.any(Job.parent_job_id.is_not(None))

    async def create_session(
        self,
        name: str | None,
        metadata_json: dict[str, Any] | None,
        *,
        multi_turn_memory: bool = True,
        context_recent_message_limit: int | None = None,
        context_recent_tool_exchange_limit: int | None = None,
    ) -> AgentSession:
        async with self._session_factory() as session, session.begin():
            item = AgentSession(
                name=name,
                metadata_json=metadata_json or {},
                multi_turn_memory=multi_turn_memory,
                context_recent_message_limit=context_recent_message_limit,
                context_recent_tool_exchange_limit=context_recent_tool_exchange_limit,
            )
            session.add(item)
            await session.flush()
            session_id = item.id
            registries_result = await session.execute(
                select(McpRegistry).where(McpRegistry.custom.is_(False))
            )
            for registry in registries_result.scalars().unique():
                session.add(
                    SessionEnabledMcp(
                        session_id=session_id,
                        mcp_name=registry.name,
                        enabled=True,
                    )
                )
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
        async with self._session_factory() as session, session.begin():
            registries_result = await session.execute(
                select(McpRegistry).where(McpRegistry.custom.is_(False))
            )
            registry_names = [
                registry.name for registry in registries_result.scalars().unique()
            ]
            if registry_names:
                sessions_result = await session.execute(
                    select(AgentSession.id).where(self._top_level_session_filter())
                )
                session_ids = list(sessions_result.scalars())
                if session_ids:
                    enabled_result = await session.execute(
                        select(
                            SessionEnabledMcp.session_id,
                            SessionEnabledMcp.mcp_name,
                        ).where(SessionEnabledMcp.session_id.in_(session_ids))
                    )
                    enabled_pairs = set(enabled_result.all())
                    for session_id in session_ids:
                        for registry_name in registry_names:
                            if (session_id, registry_name) in enabled_pairs:
                                continue
                            session.add(
                                SessionEnabledMcp(
                                    session_id=session_id,
                                    mcp_name=registry_name,
                                    enabled=True,
                                )
                            )

        async with self._session_factory() as session:
            top_level_filter = self._top_level_session_filter()
            query = self._session_query().where(top_level_filter)
            count_query = (
                select(func.count()).select_from(AgentSession).where(top_level_filter)
            )
            if status is not None:
                query = query.where(AgentSession.status == status)
                count_query = count_query.where(AgentSession.status == status)
            total = await session.scalar(count_query)
            result = await session.execute(
                query.order_by(AgentSession.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            return list(result.scalars().unique()), int(total or 0)

    async def get_session(self, session_id: str) -> AgentSession | None:
        async with self._session_factory() as session:
            result = await session.execute(
                self._session_query().where(AgentSession.id == session_id)
            )
            return result.scalars().unique().first()

    async def update_session(
        self, session_id: str, **changes: Any
    ) -> AgentSession | None:
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentSession, session_id)
            if item is None:
                return None
            if "name" in changes:
                item.name = changes["name"]
            if "metadata_json" in changes:
                item.metadata_json = changes["metadata_json"]
            if "context_recent_message_limit" in changes:
                item.context_recent_message_limit = changes[
                    "context_recent_message_limit"
                ]
            if "context_recent_tool_exchange_limit" in changes:
                item.context_recent_tool_exchange_limit = changes[
                    "context_recent_tool_exchange_limit"
                ]
            item.updated_at = utc_now()
        return await self.get_session(session_id)

    async def get_session_replay_settings(self, session_id: str) -> AgentSession | None:
        async with self._session_factory() as session:
            return await session.get(AgentSession, session_id)

    async def update_multi_turn_memory(
        self, session_id: str, *, multi_turn_memory: bool
    ) -> AgentSession | None:
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentSession, session_id)
            if item is None:
                return None
            item.multi_turn_memory = multi_turn_memory
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
                config = SessionModelConfig(
                    session_id=session_id,
                    provider_id=provider_id,
                    model_name=model_name,
                )
                session.add(config)
            config.provider_id = provider_id
            config.model_name = model_name
            config.gateway_options = gateway_options or {}
            config.provider_options = provider_options or {}
            config.updated_at = utc_now()
        session_obj = await self.get_session(session_id)
        return None if session_obj is None else session_obj.model_config

    async def add_skill_registry(
        self,
        *,
        name: str,
        skill_path: str,
        description: str | None,
        metadata_json: dict[str, Any] | None,
    ) -> SkillRegistry:
        async with self._session_factory() as session, session.begin():
            item = await session.get(SkillRegistry, name)
            if item is None:
                item = SkillRegistry(
                    name=name,
                    skill_path=skill_path,
                    description=description,
                    metadata_json=metadata_json or {},
                )
                session.add(item)
            else:
                item.skill_path = skill_path
                item.description = description
                item.metadata_json = metadata_json or {}
        return item

    async def list_skill_registries(self) -> list[SkillRegistry]:
        async with self._session_factory() as session:
            result = await session.execute(select(SkillRegistry))
            return list(result.scalars().unique())

    async def remove_skill_registry(self, name: str) -> bool:
        async with self._session_factory() as session, session.begin():
            item = await session.get(SkillRegistry, name)
            if item is None:
                return False
            await session.delete(item)
            return True

    async def enable_skill_for_session(
        self, session_id: str, skill_name: str, enabled: bool
    ) -> SessionEnabledSkill | None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            if await session.get(SkillRegistry, skill_name) is None:
                return None
            result = await session.execute(
                select(SessionEnabledSkill).where(
                    SessionEnabledSkill.session_id == session_id,
                    SessionEnabledSkill.skill_name == skill_name,
                )
            )
            item = result.scalars().first()
            if item is None:
                item = SessionEnabledSkill(
                    session_id=session_id,
                    skill_name=skill_name,
                    enabled=enabled,
                )
                session.add(item)
            else:
                item.enabled = enabled
                item.updated_at = utc_now()
        return item

    async def list_session_enabled_skills(
        self, session_id: str
    ) -> list[SessionEnabledSkill]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SessionEnabledSkill).where(
                    SessionEnabledSkill.session_id == session_id
                )
            )
            return list(result.scalars().unique())

    async def get_session_enabled_skill_state(
        self, session_id: str, skill_name: str
    ) -> SessionEnabledSkill | None:
        async with self._session_factory() as session:
            return await session.get(SessionEnabledSkill, (session_id, skill_name))

    async def add_mcp_registry(
        self,
        *,
        name: str,
        transport: str,
        server_url: str,
        headers_json: dict[str, Any] | None,
        custom: bool = True,
    ) -> McpRegistry:
        if not server_url.endswith("/"):
            server_url = server_url + "/"
        async with self._session_factory() as session, session.begin():
            item = await session.get(McpRegistry, name)
            if item is None:
                item = McpRegistry(
                    name=name,
                    transport=transport,
                    server_url=server_url,
                    headers_json=headers_json or {},
                    custom=custom,
                )
                session.add(item)
            else:
                item.transport = transport
                item.server_url = server_url
                item.headers_json = headers_json or {}
                item.custom = custom
        return item

    async def list_mcp_registries(self) -> list[McpRegistry]:
        async with self._session_factory() as session:
            result = await session.execute(select(McpRegistry))
            return list(result.scalars().unique())

    async def get_mcp_registry(self, name: str) -> McpRegistry | None:
        async with self._session_factory() as session:
            return await session.get(McpRegistry, name)

    async def remove_mcp_registry(self, name: str) -> bool:
        async with self._session_factory() as session, session.begin():
            item = await session.get(McpRegistry, name)
            if item is None:
                return False
            if not item.custom:
                return False
            enabled_result = await session.execute(
                select(SessionEnabledMcp).where(SessionEnabledMcp.mcp_name == name)
            )
            for enabled_item in enabled_result.scalars().unique():
                await session.delete(enabled_item)
            await session.delete(item)
            return True

    async def enable_mcp_for_session(
        self, session_id: str, mcp_name: str, enabled: bool
    ) -> SessionEnabledMcp | None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            if await session.get(McpRegistry, mcp_name) is None:
                return None
            result = await session.execute(
                select(SessionEnabledMcp).where(
                    SessionEnabledMcp.session_id == session_id,
                    SessionEnabledMcp.mcp_name == mcp_name,
                )
            )
            item = result.scalars().first()
            if item is None:
                item = SessionEnabledMcp(
                    session_id=session_id,
                    mcp_name=mcp_name,
                    enabled=enabled,
                )
                session.add(item)
            else:
                item.enabled = enabled
                item.updated_at = utc_now()
        return item

    async def list_session_enabled_mcps(
        self, session_id: str
    ) -> list[SessionEnabledMcp]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SessionEnabledMcp).where(
                    SessionEnabledMcp.session_id == session_id
                )
            )
            return list(result.scalars().unique())

    async def get_session_enabled_mcp_state(
        self, session_id: str, mcp_name: str
    ) -> SessionEnabledMcp | None:
        async with self._session_factory() as session:
            return await session.get(SessionEnabledMcp, (session_id, mcp_name))

    # Backward-compatible methods for old skill assignment API
    async def add_skill_assignment(
        self, session_id: str, skill_name: str, skill_path: str
    ) -> SessionEnabledSkill | None:
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            existing = await session.get(SkillRegistry, skill_name)
            if existing is None:
                existing = SkillRegistry(
                    name=skill_name,
                    skill_path=skill_path,
                    description=None,
                    metadata_json={},
                )
                session.add(existing)
            result = await session.execute(
                select(SessionEnabledSkill).where(
                    SessionEnabledSkill.session_id == session_id,
                    SessionEnabledSkill.skill_name == skill_name,
                )
            )
            item = result.scalars().first()
            if item is None:
                item = SessionEnabledSkill(
                    session_id=session_id,
                    skill_name=skill_name,
                    enabled=True,
                )
                session.add(item)
            else:
                item.enabled = True
                item.updated_at = utc_now()
        return item

    async def remove_skill_assignment(self, session_id: str, skill_name: str) -> bool:
        async with self._session_factory() as session, session.begin():
            item = await session.get(SessionEnabledSkill, (session_id, skill_name))
            if item is None:
                return False
            await session.delete(item)
            return True

    async def get_skill_assignment(self, session_id: str) -> SessionEnabledSkill | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SessionEnabledSkill).where(
                    SessionEnabledSkill.session_id == session_id
                )
            )
            return result.scalars().first()
