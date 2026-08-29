from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select, update

from agent_orchestrator.repositories.base import utc_now
from agent_orchestrator.runtime.session_modes import SESSION_MODE_CHAT
from agent_orchestrator.storage.models import (
    AgentPersona,
    AgentSession,
    CompactionRecord,
    Job,
    JobEvent,
    JobOutput,
    JobQuestion,
    McpRegistry,
    PlayerIllegalAction,
    PlayerMessage,
    SessionAllowedSubagent,
    SessionEnabledMcp,
    SessionModelConfig,
    SessionEnabledSkill,
    SessionPlayerConfig,
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
        session_mode: str = SESSION_MODE_CHAT,
        context_recent_message_limit: int | None = None,
        context_recent_tool_exchange_limit: int | None = None,
        default_subagent_persona: str | None = None,
        session_persona: str | None = None,
    ) -> AgentSession:
        async with self._session_factory() as session, session.begin():
            item = AgentSession(
                name=name,
                metadata_json=metadata_json or {},
                multi_turn_memory=multi_turn_memory,
                session_mode=session_mode,
                context_recent_message_limit=context_recent_message_limit,
                context_recent_tool_exchange_limit=context_recent_tool_exchange_limit,
                default_subagent_persona=default_subagent_persona,
                session_persona=session_persona,
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

    async def get_active_session_by_game_id(self, game_id: str) -> AgentSession | None:
        """Return the most recently created active session bound to a game_id.

        The game_id correlation identifier is stored in ``metadata_json`` by the
        history emitter. JSON containment varies across backends, so this loads
        active sessions and matches in Python to stay dialect-agnostic.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                self._session_query()
                .where(AgentSession.status == "active")
                .order_by(AgentSession.created_at.desc())
            )
            for item in result.scalars().unique():
                metadata = item.metadata_json or {}
                if metadata.get("game_id") == game_id:
                    return item
            return None

    async def update_session(
        self,
        session_id: str,
        *,
        preserve_metadata_keys: set[str] | None = None,
        **changes: Any,
    ) -> AgentSession | None:
        """Update a session, optionally preserving server-owned metadata keys.

        The protected metadata is merged inside the same transaction that writes
        the row. Callers that prepared a replacement from an earlier read can
        therefore not erase a binding captured concurrently.
        """
        async with self._session_factory() as session, session.begin():
            item = await session.get(
                AgentSession,
                session_id,
                with_for_update=preserve_metadata_keys is not None,
            )
            if item is None:
                return None
            if "name" in changes:
                item.name = changes["name"]
            if "metadata_json" in changes:
                metadata = changes["metadata_json"]
                if preserve_metadata_keys:
                    merged_metadata = dict(metadata)
                    current_metadata = item.metadata_json or {}
                    for key in preserve_metadata_keys:
                        if key in current_metadata:
                            merged_metadata[key] = current_metadata[key]
                    metadata = merged_metadata
                item.metadata_json = metadata
            if "context_recent_message_limit" in changes:
                item.context_recent_message_limit = changes[
                    "context_recent_message_limit"
                ]
            if "context_recent_tool_exchange_limit" in changes:
                item.context_recent_tool_exchange_limit = changes[
                    "context_recent_tool_exchange_limit"
                ]
            if "default_subagent_persona" in changes:
                item.default_subagent_persona = changes["default_subagent_persona"]
            if "session_persona" in changes:
                item.session_persona = changes["session_persona"]
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

    async def update_session_mode(
        self, session_id: str, *, session_mode: str
    ) -> tuple[AgentSession | None, str | None]:
        """Change a session's mode, refusing once the session has run a job.

        Returns ``(session, None)`` on success and ``(None, reason)`` when the
        change is refused, so the router can answer 409 with the reason rather
        than re-deriving it. Setting the mode to the value it already holds is a
        no-op and is always allowed, so a client that echoes the current mode back
        on an unrelated save is never refused.

        The refusal is not a policy choice: an orchestrated session's seats own
        persistent sessions recorded in ``session_player_configs``. Leaving
        orchestrated mode abandons them, and entering it would begin seat-scoping
        a conversation whose agent holds no seat.
        """
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentSession, session_id)
            if item is None:
                return None, None
            if item.session_mode == session_mode:
                return await self.get_session(session_id), None
            job_count = await session.scalar(
                select(func.count())
                .select_from(Job)
                .where(Job.session_id == session_id)
            )
            if job_count:
                return None, (
                    "A session's mode cannot change once it has run a prompt."
                )
            item.session_mode = session_mode
            item.updated_at = utc_now()
        return await self.get_session(session_id), None

    async def terminate_session(self, session_id: str) -> AgentSession | None:
        async with self._session_factory() as session, session.begin():
            item = await session.get(AgentSession, session_id)
            if item is None:
                return None
            item.status = "terminated"
            item.terminated_at = utc_now()
            item.updated_at = utc_now()
        return await self.get_session(session_id)

    async def delete_session(self, session_id: str) -> bool:
        """Hard-delete a session together with every row that hangs off it.

        Returns ``False`` when the session does not exist so the caller can
        answer 404, mirroring ``delete_player_config``.

        Every dependent row is deleted explicitly instead of leaning on the
        declared ``ON DELETE CASCADE`` foreign keys: SQLite (which backs the test
        suites) does not enforce foreign keys unless the per-connection pragma is
        set, and ``compaction_records`` has no ORM cascade from ``AgentSession``
        at all. Deleting explicitly keeps Postgres and SQLite behaviour identical
        and leaves no orphaned transcript rows on either.
        """
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return False

            job_ids = list(
                (
                    await session.execute(
                        select(Job.id).where(Job.session_id == session_id)
                    )
                ).scalars()
            )
            if job_ids:
                # Subagent jobs in other sessions can point at these jobs; drop
                # the reference the way the FK's ON DELETE SET NULL would.
                await session.execute(
                    update(Job)
                    .where(Job.parent_job_id.in_(job_ids))
                    .values(parent_job_id=None)
                )
                await session.execute(
                    delete(JobEvent).where(JobEvent.job_id.in_(job_ids))
                )
                await session.execute(
                    delete(JobOutput).where(JobOutput.job_id.in_(job_ids))
                )
            # Events also carry a session_id, so sweep any that outlived their job.
            await session.execute(
                delete(JobEvent).where(JobEvent.session_id == session_id)
            )
            # Questions do too, and a pending one must not survive its session:
            # nothing is left to read its answer.
            await session.execute(
                delete(JobQuestion).where(JobQuestion.session_id == session_id)
            )
            # Compaction records reference jobs, so they go before the jobs do.
            await session.execute(
                delete(CompactionRecord).where(
                    CompactionRecord.session_id == session_id
                )
            )
            await session.execute(delete(Job).where(Job.session_id == session_id))
            await session.execute(
                delete(SessionEnabledSkill).where(
                    SessionEnabledSkill.session_id == session_id
                )
            )
            await session.execute(
                delete(SessionEnabledMcp).where(
                    SessionEnabledMcp.session_id == session_id
                )
            )
            await session.execute(
                delete(SessionPlayerConfig).where(
                    SessionPlayerConfig.session_id == session_id
                )
            )
            await session.execute(
                delete(SessionAllowedSubagent).where(
                    SessionAllowedSubagent.session_id == session_id
                )
            )
            # The player channel and the findings hang off the ORCHESTRATING
            # session, so deleting a table takes both with it. They are swept
            # explicitly for the same reason every other dependent row is: the
            # declared cascade is not enforced on SQLite without the
            # per-connection pragma, so relying on it would leave the test suites
            # passing while real rows survived their session.
            await session.execute(
                delete(PlayerMessage).where(PlayerMessage.session_id == session_id)
            )
            await session.execute(
                delete(PlayerIllegalAction).where(
                    PlayerIllegalAction.session_id == session_id
                )
            )
            await session.execute(
                delete(SessionModelConfig).where(
                    SessionModelConfig.session_id == session_id
                )
            )
            await session.execute(
                delete(AgentSession).where(AgentSession.id == session_id)
            )
            return True

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

    async def set_subagent_allowed(
        self, session_id: str, persona_name: str, enabled: bool
    ) -> SessionAllowedSubagent | None:
        """Allow or disallow one persona for this session's spawns.

        Mirrors :meth:`enable_skill_for_session`: the row is created on first use
        and thereafter toggled rather than deleted, and a name with no
        ``agent_personas`` row is refused with ``None`` so the caller can answer
        400 instead of writing a dangling reference.
        """
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return None
            if await session.get(AgentPersona, persona_name) is None:
                return None
            item = await session.get(SessionAllowedSubagent, (session_id, persona_name))
            if item is None:
                item = SessionAllowedSubagent(
                    session_id=session_id,
                    persona_name=persona_name,
                    enabled=enabled,
                )
                session.add(item)
            else:
                item.enabled = enabled
                item.updated_at = utc_now()
        return item

    async def replace_session_allowed_subagents(
        self, session_id: str, persona_names: list[str]
    ) -> bool:
        """Make the session's allowlist exactly ``persona_names``, in one write.

        The per-persona endpoints exist too, and mirror the skill endpoints, but a
        client that holds a whole configuration — the dashboard's settings panel —
        needs the list applied atomically. Applying it one call at a time makes the
        session pass through states nobody asked for: a moment where the default
        subagent persona is no longer allowed, which a validating write would then
        refuse. Returns ``False`` when the session does not exist.
        """
        requested = list(dict.fromkeys(persona_names))
        async with self._session_factory() as session, session.begin():
            if await session.get(AgentSession, session_id) is None:
                return False
            existing_result = await session.execute(
                select(SessionAllowedSubagent).where(
                    SessionAllowedSubagent.session_id == session_id
                )
            )
            existing = {item.persona_name: item for item in existing_result.scalars()}
            for name in requested:
                item = existing.pop(name, None)
                if item is None:
                    session.add(
                        SessionAllowedSubagent(
                            session_id=session_id,
                            persona_name=name,
                            enabled=True,
                        )
                    )
                elif not item.enabled:
                    item.enabled = True
                    item.updated_at = utc_now()
            # Anything the client did not list is removed rather than left
            # disabled: this call states the whole allowlist, so a row it omitted
            # is a row it says should not be there.
            for leftover in existing.values():
                await session.delete(leftover)
            return True

    async def list_session_allowed_subagents(
        self, session_id: str
    ) -> list[SessionAllowedSubagent]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(SessionAllowedSubagent)
                .where(SessionAllowedSubagent.session_id == session_id)
                .order_by(SessionAllowedSubagent.persona_name)
            )
            return list(result.scalars().unique())

    async def remove_subagent_allowance(
        self, session_id: str, persona_name: str
    ) -> bool:
        async with self._session_factory() as session, session.begin():
            item = await session.get(SessionAllowedSubagent, (session_id, persona_name))
            if item is None:
                return False
            await session.delete(item)
            return True

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
