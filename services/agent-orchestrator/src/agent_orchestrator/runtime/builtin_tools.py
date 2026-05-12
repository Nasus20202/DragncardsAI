from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository

logger = logging.getLogger(__name__)

# Type alias for a builtin handler callable
# Receives (arguments, context) and returns an MCP-style tool result dict
BuiltinHandler = Callable[..., Any]


class BuiltinToolDefinition:
    """Descriptor for a built-in tool."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: BuiltinHandler,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler


class BuiltinToolRegistry:
    """Registry of built-in tools dispatched before MCP lookup."""

    def __init__(self) -> None:
        self._tools: dict[str, BuiltinToolDefinition] = {}

    def register(self, definition: BuiltinToolDefinition) -> None:
        self._tools[definition.name] = definition

    def get(self, name: str) -> BuiltinToolDefinition | None:
        return self._tools.get(name)

    def as_openai_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def list_definitions(self) -> list[BuiltinToolDefinition]:
        return list(self._tools.values())


def _text_result(text: str, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "is_error": is_error,
        "content": [{"type": "text", "text": text}],
    }


def make_load_skill_handler(
    skill_registry: SkillRegistry,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    skill_assignments: list[Any],
) -> BuiltinHandler:
    """Return a load_skill handler bound to the current job context."""

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        skill_name: str = arguments.get("skill_name", "")
        assigned_names = {a.skill_name for a in skill_assignments}
        if skill_name not in assigned_names:
            return _text_result(
                f"Skill '{skill_name}' is not assigned to this session.",
                is_error=True,
            )
        try:
            content = skill_registry.load_skill_content(skill_name)
        except FileNotFoundError:
            return _text_result(
                f"Skill '{skill_name}' content could not be loaded.",
                is_error=True,
            )
        definition = skill_registry.resolve(skill_name)
        ref_count = 0
        if definition is not None:
            ref_count = len(skill_registry.list_reference_files(skill_name))

        await repository.append_event(
            job_id,
            session_id,
            "skill_loaded",
            {"skill_name": skill_name, "reference_file_count": ref_count},
        )
        await live_event_bus.publish(
            job_id,
            "skill_loaded",
            {"skill_name": skill_name, "reference_file_count": ref_count},
        )
        return _text_result(content)

    return handle


def make_load_skill_reference_handler(
    skill_registry: SkillRegistry,
    skill_assignments: list[Any],
) -> BuiltinHandler:
    """Return a load_skill_reference handler bound to the current job context."""

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        skill_name: str = arguments.get("skill_name", "")
        reference_name: str = arguments.get("reference_name", "")
        assigned_names = {a.skill_name for a in skill_assignments}
        if skill_name not in assigned_names:
            return _text_result(
                f"Skill '{skill_name}' is not assigned to this session.",
                is_error=True,
            )
        if not reference_name:
            return _text_result("reference_name is required.", is_error=True)
        try:
            content = skill_registry.load_reference_content(skill_name, reference_name)
        except FileNotFoundError:
            return _text_result(
                f"Reference '{reference_name}' could not be loaded for skill '{skill_name}'.",
                is_error=True,
            )
        return _text_result(content)

    return handle


TERMINAL_EVENT_TYPES = frozenset({"completion", "failure", "cancellation"})


def is_master_job(job: Any) -> bool:
    """Return True if the job is a master (top-level) job that may spawn subagents."""
    return job.parent_job_id is None and job.job_type == "prompt"


def make_spawn_subagent_handler(
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    job: Any,
    schedule_child_fn: Callable[[str], Any] | None = None,
) -> BuiltinHandler:
    """Return a spawn_subagent handler bound to the current parent job context.

    The handler returns immediately after enqueuing the child job. A detached
    background task monitors the child and appends subagent_completed /
    subagent_failed to the parent job when the child reaches a terminal state.

    schedule_child_fn: optional async callable(child_job_id) that starts the child
    job concurrently (used to avoid deadlock when only one worker is running).
    """

    async def _monitor_child(
        child_job_id: str,
        child_session_id: str,
        name: str,
    ) -> None:
        """Background task: wait for child terminal event, update parent job."""
        try:
            subscriber = await live_event_bus.subscribe(child_job_id)
            terminal_event: dict[str, Any] | None = None
            try:
                while True:
                    event = await subscriber.get(timeout_seconds=600)
                    if event is None:
                        logger.warning(
                            "Parent job %s timed out waiting for child job %s",
                            job_id,
                            child_job_id,
                        )
                        terminal_event = {"type": "timeout"}
                        break
                    if event.event_type in TERMINAL_EVENT_TYPES:
                        terminal_event = {
                            "type": event.event_type,
                            **event.payload_json,
                        }
                        break
            finally:
                await subscriber.aclose()

            success = (
                terminal_event is not None
                and terminal_event.get("type") == "completion"
            )
            outcome_event_type = "subagent_completed" if success else "subagent_failed"
            outcome_payload: dict[str, Any] = {
                "child_job_id": child_job_id,
                "child_session_id": child_session_id,
                "name": name,
            }
            if not success:
                outcome_payload["reason"] = (
                    terminal_event.get("type") if terminal_event else "unknown"
                )

            try:
                await repository.append_event(
                    job_id, session_id, outcome_event_type, outcome_payload
                )
                await live_event_bus.publish(
                    job_id, outcome_event_type, outcome_payload
                )
            except Exception:
                logger.exception(
                    "Failed to append %s for parent job %s", outcome_event_type, job_id
                )
        except Exception:
            logger.exception(
                "_monitor_child raised unexpectedly for parent job %s child job %s",
                job_id,
                child_job_id,
            )

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        if not is_master_job(job):
            return _text_result(
                "spawn_subagent may only be called from a top-level (master) job.",
                is_error=True,
            )

        prompt: str = arguments.get("prompt", "")
        if not prompt:
            return _text_result("prompt is required.", is_error=True)

        name = prompt[:50]

        # Create child session inheriting model config from parent session
        parent_session = await repository.get_session(session_id)
        if parent_session is None:
            return _text_result("Parent session not found.", is_error=True)

        child_session = await repository.create_session(
            name,
            {},
            multi_turn_memory=False,
        )

        # Copy model config from parent to child
        if parent_session.model_config is not None:
            mc = parent_session.model_config
            await repository.set_model_config(
                child_session.id,
                provider_id=mc.provider_id,
                model_name=mc.model_name,
                gateway_options=mc.gateway_options,
                provider_options=mc.provider_options,
            )

        # Copy skill assignments from parent to child
        for sa in parent_session.skill_assignments:
            await repository.add_skill_assignment(
                child_session.id, sa.skill_name, sa.skill_path
            )

        # Enqueue the child job
        child_job = await repository.enqueue_prompt_job(
            child_session.id,
            prompt=prompt,
            metadata_json={"parent_job_id": job_id},
            max_attempts=1,
        )
        if child_job is None:
            return _text_result("Failed to enqueue child job.", is_error=True)

        # Stamp parent_job_id on the child job row
        await repository.set_parent_job_id(child_job.id, job_id)

        child_job_id = child_job.id

        # Emit subagent_started on parent job (includes name for dashboard)
        started_payload: dict[str, Any] = {
            "child_job_id": child_job_id,
            "child_session_id": child_session.id,
            "name": name,
        }
        await repository.append_event(
            job_id, session_id, "subagent_started", started_payload
        )
        await live_event_bus.publish(job_id, "subagent_started", started_payload)

        # Launch background monitor BEFORE scheduling so we don't miss events.
        asyncio.create_task(
            _monitor_child(child_job_id, child_session.id, name),
            name=f"monitor-child-{child_job_id}",
        )

        # Schedule the child job to run concurrently.
        if schedule_child_fn is not None:
            asyncio.create_task(schedule_child_fn(child_job_id))

        # Return immediately — the parent agent continues without waiting.
        return _text_result(f'{{"child_job_id": "{child_job_id}", "name": "{name}"}}')

    return handle


def make_wait_for_subagent_handler(
    live_event_bus: LiveEventBus,
    repository: Repository,
) -> BuiltinHandler:
    """Return a wait_for_subagent handler that blocks until a child job terminates."""

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        child_job_id: str = arguments.get("child_job_id", "")
        if not child_job_id:
            return _text_result("child_job_id is required.", is_error=True)

        # Check if the child job is already terminal (avoid hanging on a done job).
        child_job = await repository.get_job(child_job_id)
        if child_job is None:
            return _text_result(
                f"No job found with id '{child_job_id}'.", is_error=True
            )

        if child_job.status in ("completed", "failed", "cancelled"):
            # Already done — return result directly.
            if child_job.status == "completed":
                return _text_result(child_job.result_text or "Subagent completed.")
            return _text_result(
                f"Subagent ended with status: {child_job.status}.",
                is_error=True,
            )

        # Subscribe and wait for terminal event.
        subscriber = await live_event_bus.subscribe(child_job_id)
        terminal_event: dict[str, Any] | None = None
        try:
            while True:
                event = await subscriber.get(timeout_seconds=600)
                if event is None:
                    logger.warning(
                        "wait_for_subagent timed out on child job %s", child_job_id
                    )
                    terminal_event = {"type": "timeout"}
                    break
                if event.event_type in TERMINAL_EVENT_TYPES:
                    terminal_event = {"type": event.event_type, **event.payload_json}
                    break
        finally:
            await subscriber.aclose()

        if terminal_event and terminal_event.get("type") == "completion":
            return _text_result(terminal_event.get("text", "") or "Subagent completed.")
        reason = terminal_event.get("type", "unknown") if terminal_event else "unknown"
        return _text_result(f"Subagent ended with: {reason}", is_error=True)

    return handle


def build_builtin_registry(
    skill_registry: SkillRegistry,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    skill_assignments: list[Any],
    job: Any,
    schedule_child_fn: Callable[[str], Any] | None = None,
) -> BuiltinToolRegistry:
    """Build a per-job BuiltinToolRegistry with all handlers bound to job context.

    schedule_child_fn: optional async callable(child_job_id) called concurrently
    after enqueueing a child job, to avoid single-worker deadlock.
    """
    registry = BuiltinToolRegistry()

    registry.register(
        BuiltinToolDefinition(
            name="load_skill",
            description=(
                "Load an assigned skill by name. Returns SKILL.md and a list of available references. "
                "Call this before using a skill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "The name of the skill to load.",
                    }
                },
                "required": ["skill_name"],
            },
            handler=make_load_skill_handler(
                skill_registry=skill_registry,
                repository=repository,
                live_event_bus=live_event_bus,
                session_id=session_id,
                job_id=job_id,
                skill_assignments=skill_assignments,
            ),
        )
    )

    registry.register(
        BuiltinToolDefinition(
            name="load_skill_reference",
            description=(
                "Load one markdown reference file for an assigned skill after inspecting the skill's reference list."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "description": "The name of the skill that owns the reference.",
                    },
                    "reference_name": {
                        "type": "string",
                        "description": "The markdown filename listed by load_skill, for example rules.md.",
                    },
                },
                "required": ["skill_name", "reference_name"],
            },
            handler=make_load_skill_reference_handler(
                skill_registry=skill_registry,
                skill_assignments=skill_assignments,
            ),
        )
    )

    if is_master_job(job):
        registry.register(
            BuiltinToolDefinition(
                name="spawn_subagent",
                description=(
                    "Spawn a child agent with a given prompt. Returns immediately with "
                    "child_job_id and name; the child runs in parallel. You may spawn "
                    "multiple subagents and continue working without waiting."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "The prompt to send to the child agent.",
                        }
                    },
                    "required": ["prompt"],
                },
                handler=make_spawn_subagent_handler(
                    repository=repository,
                    live_event_bus=live_event_bus,
                    session_id=session_id,
                    job_id=job_id,
                    job=job,
                    schedule_child_fn=schedule_child_fn,
                ),
            )
        )

        registry.register(
            BuiltinToolDefinition(
                name="wait_for_subagent",
                description=(
                    "Wait for a previously spawned subagent to finish and return its result. "
                    "Use the child_job_id returned by spawn_subagent. "
                    "Blocks until the child completes or fails."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "child_job_id": {
                            "type": "string",
                            "description": "The child_job_id returned by spawn_subagent.",
                        }
                    },
                    "required": ["child_job_id"],
                },
                handler=make_wait_for_subagent_handler(
                    live_event_bus=live_event_bus,
                    repository=repository,
                ),
            )
        )

    return registry
