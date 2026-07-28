from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agent_orchestrator.runtime.history_emitter import SESSION_GAME_ID_KEY
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
    SESSION_PLAYER_NAME_KEY,
    ResolvedPlayerAgentConfig,
    resolve_player_agent_config,
    resolve_roster,
)
from agent_orchestrator.runtime.skills import SkillRegistry, enabled_skill_assignments
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


# Statuses a job never leaves. `interrupted` belongs here: the run hit the tool
# round limit, and the partial work it recorded is final for that job.
TERMINAL_JOB_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})

# Live events map onto outcome kinds, which are otherwise named after job
# statuses so a caller never has to know which source an outcome came from.
_EVENT_TYPE_TO_OUTCOME_KIND = {
    "completion": "completed",
    "failure": "failed",
    "cancellation": "cancelled",
}

DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS = 600.0
DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS = 5.0


def is_master_job(job: Any) -> bool:
    """Return True if the job is a master (top-level) job that may spawn subagents."""
    return job.parent_job_id is None and job.job_type == "prompt"


@dataclass(frozen=True)
class ChildOutcome:
    """How a child job ended, as far as the parent was able to observe.

    ``kind`` is a terminal job status (``completed``, ``failed``, ``cancelled``,
    ``interrupted``) when the child reached one, or describes why the parent
    stopped observing: ``missing`` (the job row is gone), ``timeout`` (the wait
    budget ran out), ``abandoned`` (the parent itself was cancelled).
    """

    kind: str
    text: str = ""
    error_code: str | None = None
    error_message: str | None = None
    last_status: str | None = None

    @property
    def has_result(self) -> bool:
        """True when the child produced usable output for the parent."""
        return self.kind in ("completed", "interrupted")


def _outcome_from_job(job: Any) -> ChildOutcome | None:
    """Read a terminal outcome off a persisted job row, or None if still live."""
    if job.status not in TERMINAL_JOB_STATUSES:
        return None
    return ChildOutcome(
        kind=job.status,
        text=job.result_text or "",
        error_code=job.error_code,
        error_message=job.error_message,
        last_status=job.status,
    )


def _outcome_from_event(event: Any) -> ChildOutcome | None:
    """Read a terminal outcome off a live event, or None if it is not terminal."""
    kind = _EVENT_TYPE_TO_OUTCOME_KIND.get(event.event_type)
    if kind is None:
        return None
    payload = event.payload_json or {}
    return ChildOutcome(
        kind=kind,
        text=payload.get("text", "") or "",
        error_code=payload.get("code"),
        error_message=payload.get("message") or payload.get("reason"),
        last_status=kind,
    )


async def _next_event(subscriber: Any, seconds: float) -> Any | None:
    """Wait up to ``seconds`` for the next event on a subscription.

    Consumes the whole interval when nothing arrives. A subscriber that reports
    "nothing yet" faster than it was asked to wait — a Valkey stream reader
    whose connection is re-establishing, for instance — would otherwise turn the
    surrounding wait into a busy loop.
    """
    started = time.monotonic()
    event = await subscriber.get(timeout_seconds=seconds)
    if event is not None:
        return event
    shortfall = seconds - (time.monotonic() - started)
    if shortfall > 0:
        await asyncio.sleep(shortfall)
    return None


async def resolve_child_outcome(
    *,
    repository: Repository,
    live_event_bus: LiveEventBus,
    child_job_id: str,
    timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS,
    abandon_when: Callable[[], Awaitable[bool]] | None = None,
) -> ChildOutcome:
    """Wait for a child job to end, bounded by an absolute deadline.

    The child's persisted status is the authority. Live events are ephemeral —
    the Valkey stream carrying them has a TTL, and not every terminal
    transition publishes one: a run that crashes out of its own failure
    handling is marked ``failed`` in the database by the worker's last-resort
    guard without announcing anything. Waiting on events alone therefore turns
    a crashed child into a silent stall, so every poll re-reads the row and any
    terminal status wins.

    Events are still consumed, so the ordinary case returns the moment the
    child finishes rather than on the next poll. A terminal event is trusted as
    it arrives because it is published just before the matching row update.

    ``timeout_seconds`` is an absolute budget, not a per-event one: a child
    stuck in a loop keeps emitting reasoning and output events, and refreshing
    the budget on each of them would let it hold the parent forever.
    """
    deadline = time.monotonic() + timeout_seconds
    last_status: str | None = None

    # Subscribing before the first read means an event published while we are
    # reading is queued rather than missed.
    subscriber = await live_event_bus.subscribe(child_job_id)
    try:
        while True:
            child_job = await repository.get_job(child_job_id)
            if child_job is None:
                return ChildOutcome(kind="missing", last_status=last_status)
            last_status = child_job.status
            outcome = _outcome_from_job(child_job)
            if outcome is not None:
                return outcome

            if abandon_when is not None and await abandon_when():
                return ChildOutcome(kind="abandoned", last_status=last_status)

            # Consume events for one poll interval before reading the row again.
            # A streaming child emits hundreds of events, and re-reading on each
            # of them would put the database on the hot path for nothing; going
            # by elapsed time instead means a chattering child can neither
            # suppress the re-read nor delay noticing the parent's cancellation.
            next_poll_at = time.monotonic() + poll_interval_seconds
            while True:
                now = time.monotonic()
                if now >= next_poll_at:
                    break
                if now >= deadline:
                    logger.warning(
                        "Gave up after %.0fs waiting for child job %s (last status %s)",
                        timeout_seconds,
                        child_job_id,
                        last_status,
                    )
                    return ChildOutcome(kind="timeout", last_status=last_status)
                event = await _next_event(subscriber, min(next_poll_at, deadline) - now)
                if event is None:
                    continue
                outcome = _outcome_from_event(event)
                if outcome is not None:
                    return outcome
    finally:
        await subscriber.aclose()


def describe_child_outcome(child_job_id: str, outcome: ChildOutcome) -> str:
    """Render an outcome as one line the parent agent can act on."""
    if outcome.kind == "failed":
        detail = ": ".join(
            part for part in (outcome.error_code, outcome.error_message) if part
        )
        suffix = f" — {detail}" if detail else ""
        return f"Subagent {child_job_id} failed{suffix}"
    if outcome.kind == "cancelled":
        reason = outcome.error_message or "no reason recorded"
        return f"Subagent {child_job_id} was cancelled — {reason}"
    if outcome.kind == "missing":
        return f"No job found with id '{child_job_id}'."
    if outcome.kind == "abandoned":
        return (
            f"Stopped waiting for subagent {child_job_id} because this job was "
            "cancelled."
        )
    if outcome.kind == "timeout":
        if outcome.last_status == "running":
            cause = (
                "it is still recorded as running, so the worker executing it may "
                "have died"
            )
        elif outcome.last_status == "queued":
            cause = "it was never picked up by a worker"
        else:
            cause = f"its last recorded status is '{outcome.last_status}'"
        return (
            f"Gave up waiting for subagent {child_job_id} — {cause}. Do not wait "
            "on it again; continue without its result or report the stall."
        )
    return f"Subagent {child_job_id} ended with status '{outcome.kind}'."


def _make_child_monitor(
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS,
) -> Callable[..., Any]:
    """Build the background watcher that reports a child's outcome to its parent."""

    async def _monitor_child(
        child_job_id: str,
        child_session_id: str,
        name: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        """Background task: wait for the child to end, update the parent job."""
        try:
            outcome = await resolve_child_outcome(
                repository=repository,
                live_event_bus=live_event_bus,
                child_job_id=child_job_id,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval_seconds,
            )
            outcome_event_type = (
                "subagent_completed" if outcome.has_result else "subagent_failed"
            )
            outcome_payload: dict[str, Any] = {
                "child_job_id": child_job_id,
                "child_session_id": child_session_id,
                "name": name,
                **(extra_payload or {}),
            }
            if not outcome.has_result:
                outcome_payload["reason"] = outcome.kind
                if outcome.error_code:
                    outcome_payload["error_code"] = outcome.error_code
                if outcome.error_message:
                    outcome_payload["error_message"] = outcome.error_message

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

    return _monitor_child


async def _launch_child_agent(
    *,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    parent_session: Any,
    prompt: str,
    name: str,
    child_metadata: dict[str, Any],
    model_config: ResolvedPlayerAgentConfig | None,
    skills: list[str] | None,
    schedule_child_fn: Callable[[str], Any] | None,
    monitor: Callable[..., Any],
    event_payload_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create, announce, monitor, and schedule a child agent session.

    Shared by ``spawn_subagent`` (which inherits the parent's configuration) and
    ``prompt_player_agent`` (which supplies a seat's own configuration). Passing
    ``model_config``/``skills`` as ``None`` means "copy the parent's".

    MCP servers are always inherited: seats differ in how they think, not in
    which table they are sitting at.
    """
    child_session = await repository.create_session(
        name,
        child_metadata,
        multi_turn_memory=False,
    )

    if model_config is not None:
        # A resolved config with neither provider nor model means the parent had
        # no model config to inherit and the seat named none either. Leave the
        # child unconfigured so it fails with the normal `missing_model_config`
        # error rather than being handed empty provider/model strings.
        if model_config.provider_id and model_config.model_name:
            await repository.set_model_config(
                child_session.id,
                provider_id=model_config.provider_id,
                model_name=model_config.model_name,
                gateway_options=model_config.gateway_options,
                provider_options=model_config.provider_options,
            )
    elif parent_session.model_config is not None:
        mc = parent_session.model_config
        await repository.set_model_config(
            child_session.id,
            provider_id=mc.provider_id,
            model_name=mc.model_name,
            gateway_options=mc.gateway_options,
            provider_options=mc.provider_options,
        )

    if skills is None:
        skill_names = [
            es.skill_name
            for es in enabled_skill_assignments(parent_session.enabled_skills)
        ]
    else:
        skill_names = skills
    for skill_name in skill_names:
        await repository.enable_skill_for_session(child_session.id, skill_name, True)

    for em in parent_session.enabled_mcps:
        if em.enabled:
            await repository.enable_mcp_for_session(
                child_session.id, em.mcp_name, em.enabled
            )

    child_job = await repository.enqueue_prompt_job(
        child_session.id,
        prompt=prompt,
        metadata_json={"parent_job_id": job_id, **(event_payload_extra or {})},
        max_attempts=1,
    )
    if child_job is None:
        return _text_result("Failed to enqueue child job.", is_error=True)

    await repository.set_parent_job_id(child_job.id, job_id)
    child_job_id = child_job.id

    started_payload: dict[str, Any] = {
        "child_job_id": child_job_id,
        "child_session_id": child_session.id,
        "name": name,
        **(event_payload_extra or {}),
    }
    await repository.append_event(
        job_id, session_id, "subagent_started", started_payload
    )
    await live_event_bus.publish(job_id, "subagent_started", started_payload)

    # Launch background monitor BEFORE scheduling so we don't miss events.
    asyncio.create_task(
        monitor(child_job_id, child_session.id, name, event_payload_extra or {}),
        name=f"monitor-child-{child_job_id}",
    )

    if schedule_child_fn is not None:
        await schedule_child_fn(child_job_id)

    # Return immediately — the parent agent continues without waiting.
    return _text_result(
        json.dumps(
            {
                "child_job_id": child_job_id,
                "name": name,
                **(event_payload_extra or {}),
            }
        )
    )


def make_spawn_subagent_handler(
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    job: Any,
    schedule_child_fn: Callable[[str], Any] | None = None,
    monitor_timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    monitor_poll_interval_seconds: float = DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS,
) -> BuiltinHandler:
    """Return a spawn_subagent handler bound to the current parent job context.

    The handler returns immediately after enqueuing the child job. A detached
    background task monitors the child and appends subagent_completed /
    subagent_failed to the parent job when the child reaches a terminal state.

    schedule_child_fn: optional async callable(child_job_id) that starts the child
    job concurrently (used to avoid deadlock when only one worker is running).
    """
    monitor = _make_child_monitor(
        repository,
        live_event_bus,
        session_id,
        job_id,
        timeout_seconds=monitor_timeout_seconds,
        poll_interval_seconds=monitor_poll_interval_seconds,
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

        parent_session = await repository.get_session(session_id)
        if parent_session is None:
            return _text_result("Parent session not found.", is_error=True)

        return await _launch_child_agent(
            repository=repository,
            live_event_bus=live_event_bus,
            session_id=session_id,
            job_id=job_id,
            parent_session=parent_session,
            prompt=prompt,
            name=name,
            child_metadata={},
            model_config=None,
            skills=None,
            schedule_child_fn=schedule_child_fn,
            monitor=monitor,
        )

    return handle


def make_list_player_agents_handler(
    repository: Repository,
    session_id: str,
) -> BuiltinHandler:
    """Return a list_player_agents handler for an orchestrating session.

    Reports the *resolved* configuration per seat — what each player agent will
    actually run with after inheritance — so the orchestrator can state the
    roster accurately when reporting a game.
    """

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        del arguments
        session = await repository.get_session(session_id)
        if session is None:
            return _text_result("Session not found.", is_error=True)
        configs = await repository.list_player_configs(session_id)
        if not configs:
            return _text_result(
                "No player agents are configured for this session. "
                "Ask the user to configure at least one player before starting a game.",
                is_error=True,
            )
        roster = resolve_roster(session, configs)
        return _text_result(
            json.dumps({"players": [entry.as_summary() for entry in roster]})
        )

    return handle


def make_prompt_player_agent_handler(
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    job: Any,
    schedule_child_fn: Callable[[str], Any] | None = None,
    monitor_timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    monitor_poll_interval_seconds: float = DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS,
) -> BuiltinHandler:
    """Return a prompt_player_agent handler bound to the orchestrating job.

    The child is configured from the named seat's own stored configuration
    rather than from the parent's, which is what makes two seats comparable.
    The child session is tagged with its seat id so every move it records is
    attributed to that seat without inference, and with the orchestrator's
    ``game_id`` so its very first move lands on the right timeline.
    """
    monitor = _make_child_monitor(
        repository,
        live_event_bus,
        session_id,
        job_id,
        timeout_seconds=monitor_timeout_seconds,
        poll_interval_seconds=monitor_poll_interval_seconds,
    )

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        if not is_master_job(job):
            return _text_result(
                "prompt_player_agent may only be called from the orchestrating "
                "(top-level) job.",
                is_error=True,
            )

        player_id: str = arguments.get("player_id", "")
        prompt: str = arguments.get("prompt", "")
        if not player_id:
            return _text_result("player_id is required.", is_error=True)
        if not prompt:
            return _text_result("prompt is required.", is_error=True)

        parent_session = await repository.get_session(session_id)
        if parent_session is None:
            return _text_result("Parent session not found.", is_error=True)

        player_config = await repository.get_player_config(session_id, player_id)
        if player_config is None:
            configured = [
                c.player_id for c in await repository.list_player_configs(session_id)
            ]
            known = ", ".join(configured) if configured else "none"
            return _text_result(
                f"No player agent is configured for '{player_id}'. Configured seats: {known}.",
                is_error=True,
            )

        resolved = resolve_player_agent_config(parent_session, player_config)
        name = resolved.display_name or player_id

        child_metadata: dict[str, Any] = {
            SESSION_PLAYER_ID_KEY: player_id,
            SESSION_ORCHESTRATOR_ID_KEY: session_id,
        }
        if resolved.display_name:
            child_metadata[SESSION_PLAYER_NAME_KEY] = resolved.display_name
        parent_metadata = parent_session.metadata_json or {}
        game_id = parent_metadata.get(SESSION_GAME_ID_KEY)
        if isinstance(game_id, str) and game_id:
            child_metadata[SESSION_GAME_ID_KEY] = game_id

        return await _launch_child_agent(
            repository=repository,
            live_event_bus=live_event_bus,
            session_id=session_id,
            job_id=job_id,
            parent_session=parent_session,
            prompt=prompt,
            name=name,
            child_metadata=child_metadata,
            model_config=resolved,
            skills=resolved.skills,
            schedule_child_fn=schedule_child_fn,
            monitor=monitor,
            event_payload_extra={"player_id": player_id},
        )

    return handle


def make_wait_for_subagent_handler(
    live_event_bus: LiveEventBus,
    repository: Repository,
    session_id: str = "",
    job_id: str = "",
    timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS,
) -> BuiltinHandler:
    """Return a wait_for_subagent handler that blocks until a child job ends.

    The wait always ends: a child that crashes, is cancelled, is orphaned by a
    dead worker, or simply never reports back all produce a result the parent
    agent can reason about. Giving up is recorded on the parent job as well as
    returned, so a stalled wait is visible in the session's event stream rather
    than only in the service log.
    """

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        child_job_id: str = arguments.get("child_job_id", "")
        if not child_job_id:
            return _text_result("child_job_id is required.", is_error=True)

        async def parent_was_cancelled() -> bool:
            if not job_id:
                return False
            return await repository.get_job_cancellation_requested(job_id)

        outcome = await resolve_child_outcome(
            repository=repository,
            live_event_bus=live_event_bus,
            child_job_id=child_job_id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            abandon_when=parent_was_cancelled,
        )

        if outcome.kind == "timeout":
            await _announce_wait_timeout(
                repository=repository,
                live_event_bus=live_event_bus,
                session_id=session_id,
                job_id=job_id,
                child_job_id=child_job_id,
                outcome=outcome,
                timeout_seconds=timeout_seconds,
            )

        if outcome.has_result:
            return _text_result(outcome.text or "Subagent completed.")
        return _text_result(
            describe_child_outcome(child_job_id, outcome), is_error=True
        )

    return handle


async def _announce_wait_timeout(
    *,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    child_job_id: str,
    outcome: ChildOutcome,
    timeout_seconds: float,
) -> None:
    """Record an abandoned wait on the parent job.

    Reported as ``subagent_failed`` rather than a new event type so the existing
    session timeline shows it without any consumer change: from the parent's
    point of view a child it can no longer hear from has failed.
    """
    if not job_id or not session_id:
        return
    payload = {
        "child_job_id": child_job_id,
        "reason": "wait_timeout",
        "waited_seconds": timeout_seconds,
        "child_status": outcome.last_status,
    }
    try:
        await repository.append_event(job_id, session_id, "subagent_failed", payload)
        await live_event_bus.publish(job_id, "subagent_failed", payload)
    except Exception:
        logger.exception(
            "Failed to record the abandoned wait for child job %s on parent job %s",
            child_job_id,
            job_id,
        )


def build_builtin_registry(
    skill_registry: SkillRegistry,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    skill_assignments: list[Any],
    job: Any,
    schedule_child_fn: Callable[[str], Any] | None = None,
    player_configs: list[Any] | None = None,
    subagent_wait_timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    subagent_wait_poll_interval_seconds: float = (
        DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS
    ),
) -> BuiltinToolRegistry:
    """Build a per-job BuiltinToolRegistry with all handlers bound to job context.

    schedule_child_fn: optional async callable(child_job_id) called concurrently
    after enqueueing a child job, to avoid single-worker deadlock.

    subagent_wait_timeout_seconds / subagent_wait_poll_interval_seconds: bound
    how long the parent will wait on a child and how often it re-reads the
    child's persisted status while waiting.

    player_configs: the session's player-agent roster. The player tools are
    registered only when a roster exists, so sessions that are not running an
    orchestrated game never see tools they cannot use. The roster is passed in
    already loaded so registry construction stays synchronous.
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
                    "Spawn a child agent to handle a task in parallel. "
                    "ONLY available to top-level jobs — subagents do not have this tool and must "
                    "call MCP tools directly. "
                    "IMPORTANT: You MUST use this tool instead of calling large-payload tools "
                    "directly. Any use of search_cards_marvel_champions, get_game_state, "
                    "export_game_state_snapshot, load_game_state_snapshot, reset_game, or any "
                    "tool that returns a card list or full board JSON must be delegated here — "
                    "direct calls inject thousands of tokens into your context permanently. "
                    "Write a fully self-contained prompt (include session ID, any known card IDs, "
                    "group IDs, and exactly what to return). Returns immediately with child_job_id; "
                    "the child runs concurrently. Spawn multiple subagents before waiting for any."
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
                    monitor_timeout_seconds=subagent_wait_timeout_seconds,
                    monitor_poll_interval_seconds=subagent_wait_poll_interval_seconds,
                ),
            )
        )

        registry.register(
            BuiltinToolDefinition(
                name="wait_for_subagent",
                description=(
                    "Wait for a previously spawned subagent to finish and return its result. "
                    "Use the child_job_id returned by spawn_subagent. "
                    "Blocks until the child completes, fails, or is cancelled, and "
                    "always returns: if the child crashed you get the failure and its "
                    "cause, and if it stopped reporting altogether you get told to stop "
                    "waiting on it. Never call it twice on a child it told you to give "
                    "up on."
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
                    session_id=session_id,
                    job_id=job_id,
                    timeout_seconds=subagent_wait_timeout_seconds,
                    poll_interval_seconds=subagent_wait_poll_interval_seconds,
                ),
            )
        )

        if player_configs:
            registry.register(
                BuiltinToolDefinition(
                    name="list_player_agents",
                    description=(
                        "List the player agents configured for this game, one per seat. "
                        "Returns each seat's id, display name, and the provider, model, "
                        "reasoning, and skills it will actually run with. "
                        "Call this before starting a game to confirm the roster and the "
                        "number of players."
                    ),
                    parameters={"type": "object", "properties": {}},
                    handler=make_list_player_agents_handler(
                        repository=repository,
                        session_id=session_id,
                    ),
                )
            )

            registry.register(
                BuiltinToolDefinition(
                    name="prompt_player_agent",
                    description=(
                        "Send a prompt to one seat's player agent — the agent that plays "
                        "that hero. Use this for every decision that belongs to a player: "
                        "their turn during the player phase, and any choice an encounter "
                        "card or activation hands to that specific player. "
                        "The player agent runs with that seat's own model, reasoning, and "
                        "skills, and has NO memory of previous turns, so the prompt must be "
                        "fully self-contained: game session id, seat id, hero and form, "
                        "round number, the board summary it needs, and exactly what to "
                        "report back. Returns immediately with child_job_id; retrieve the "
                        "seat's report with wait_for_subagent. Never decide a hero's play "
                        "yourself."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "player_id": {
                                "type": "string",
                                "description": (
                                    "The seat to prompt, for example player1. Must be a "
                                    "seat returned by list_player_agents."
                                ),
                            },
                            "prompt": {
                                "type": "string",
                                "description": (
                                    "The fully self-contained prompt for this seat's turn "
                                    "or decision."
                                ),
                            },
                        },
                        "required": ["player_id", "prompt"],
                    },
                    handler=make_prompt_player_agent_handler(
                        repository=repository,
                        live_event_bus=live_event_bus,
                        session_id=session_id,
                        job_id=job_id,
                        job=job,
                        schedule_child_fn=schedule_child_fn,
                        monitor_timeout_seconds=subagent_wait_timeout_seconds,
                        monitor_poll_interval_seconds=(
                            subagent_wait_poll_interval_seconds
                        ),
                    ),
                )
            )

    return registry
