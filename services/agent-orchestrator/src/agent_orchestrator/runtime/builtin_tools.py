from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from agent_orchestrator.repositories.questions import (
    QUESTION_STATUS_ANSWERED,
    QUESTION_STATUS_CLOSED,
)
from agent_orchestrator.runtime.display_names import generate_agent_name
from agent_orchestrator.runtime.history_emitter import SESSION_GAME_ID_KEY
from agent_orchestrator.runtime.live_events import LiveEventBus
from agent_orchestrator.runtime.personas import (
    SESSION_PERSONA_KEY,
    ResolvedPersona,
    resolve_persona,
)
from agent_orchestrator.runtime.player_agents import (
    SESSION_ORCHESTRATOR_ID_KEY,
    SESSION_PLAYER_ID_KEY,
    SESSION_PLAYER_NAME_KEY,
    ResolvedPlayerAgentConfig,
    resolve_player_agent_config,
    resolve_roster,
    session_player_id,
    wrap_player_report,
)
from agent_orchestrator.runtime.session_modes import is_orchestrated
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

        skill_payload = {
            "skill_name": skill_name,
            "reference_file_count": ref_count,
        }
        durable_event_id = await repository.append_event(
            job_id, session_id, "skill_loaded", skill_payload
        )
        await live_event_bus.publish(
            job_id,
            "skill_loaded",
            skill_payload,
            durable_event_id=durable_event_id,
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
                durable_event_id = await repository.append_event(
                    job_id, session_id, outcome_event_type, outcome_payload
                )
                await live_event_bus.publish(
                    job_id,
                    outcome_event_type,
                    outcome_payload,
                    durable_event_id=durable_event_id,
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
    name: str | None,
    child_metadata: dict[str, Any],
    model_config: ResolvedPlayerAgentConfig | ResolvedPersona | None,
    skills: list[str] | None,
    schedule_child_fn: Callable[[str], Any] | None,
    monitor: Callable[..., Any],
    event_payload_extra: dict[str, Any] | None = None,
    multi_turn_memory: bool = False,
    existing_child_session: Any | None = None,
    on_child_session_created: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Create, announce, monitor, and schedule a child agent session.

    Shared by ``spawn_subagent`` (which inherits the parent's configuration) and
    ``prompt_player_agent`` (which supplies a seat's own configuration). Passing
    ``model_config``/``skills`` as ``None`` means "copy the parent's".

    MCP servers are always inherited: seats differ in how they think, not in
    which table they are sitting at.

    ``multi_turn_memory`` defaults to ``False``, which is the memoryless subagent
    every caller wanted before orchestrated mode existed. A player seat in an
    orchestrated game passes ``True`` and its session is then an ordinary
    multi-turn session: prior turns replay, auto-compaction applies, and nothing
    special is built for it.

    ``existing_child_session`` short-circuits creation and configuration entirely:
    a seat that already owns a session is prompted again on that same session, so
    its configuration is the one captured when the seat was created and is not
    re-derived (which is what makes a persona snapshot hold for a whole game).

    ``name`` is the caller's display name for the child, used when the caller
    already has a meaningful one — a seat's hero name, say. Passing ``None`` asks
    for a generated one, which is seeded on the child session's own id so that no
    two children ever share a codename. That is why the session is created
    unnamed and then named: the seed does not exist until the row does. The name
    is stored on the child session and copied into every event that mentions it,
    so no reader ever recomputes it.
    """
    if existing_child_session is not None:
        return await _enqueue_child_job(
            repository=repository,
            live_event_bus=live_event_bus,
            session_id=session_id,
            job_id=job_id,
            child_session_id=existing_child_session.id,
            prompt=prompt,
            name=name,
            schedule_child_fn=schedule_child_fn,
            monitor=monitor,
            event_payload_extra=event_payload_extra,
        )

    child_session = await repository.create_session(
        name,
        child_metadata,
        multi_turn_memory=multi_turn_memory,
    )
    if name is None:
        name = generate_agent_name(child_session.id, prompt)
        await repository.update_session(child_session.id, name=name)
    if on_child_session_created is not None:
        await on_child_session_created(child_session.id)

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

    return await _enqueue_child_job(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session_id,
        job_id=job_id,
        child_session_id=child_session.id,
        prompt=prompt,
        name=name,
        schedule_child_fn=schedule_child_fn,
        monitor=monitor,
        event_payload_extra=event_payload_extra,
    )


async def _enqueue_child_job(
    *,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    child_session_id: str,
    prompt: str,
    name: str,
    schedule_child_fn: Callable[[str], Any] | None,
    monitor: Callable[..., Any],
    event_payload_extra: dict[str, Any] | None,
) -> dict[str, Any]:
    """Enqueue, announce, monitor, and schedule one job on a child session.

    Split out of :func:`_launch_child_agent` so a seat that already owns a session
    takes exactly this path and nothing else: no second session, no re-applied
    model config, no re-read persona.
    """
    child_job = await repository.enqueue_prompt_job(
        child_session_id,
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
        "child_session_id": child_session_id,
        "name": name,
        **(event_payload_extra or {}),
    }
    durable_event_id = await repository.append_event(
        job_id, session_id, "subagent_started", started_payload
    )
    await live_event_bus.publish(
        job_id,
        "subagent_started",
        started_payload,
        durable_event_id=durable_event_id,
    )

    # Launch background monitor BEFORE scheduling so we don't miss events.
    asyncio.create_task(
        monitor(child_job_id, child_session_id, name, event_payload_extra or {}),
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


async def _resolve_spawn_persona(
    *,
    repository: Repository,
    skill_registry: SkillRegistry,
    parent_session: Any,
    requested_name: str,
) -> tuple[ResolvedPersona | None, dict[str, Any] | None]:
    """Resolve the persona a spawn should use, or the error result explaining why not.

    Precedence is: the persona the caller named, then the session's default, then
    none at all. Returning ``(None, None)`` means no persona applies and the child
    should inherit the parent exactly as it did before personas existed.

    A persona's own named skills are re-validated here, at the moment the child is
    started, because the skill catalogue mirrors the filesystem and is re-synced
    at every boot — a skill can stop existing between writing a persona and using
    it. A missing skill fails the spawn by name rather than being dropped
    silently, and nothing is created. Skills the persona INHERITED from the
    session are not re-checked: they are the session's own assignments, not
    something this persona claimed.
    """
    name = requested_name or (
        getattr(parent_session, "default_subagent_persona", None) or ""
    )
    if not name:
        return None, None

    persona = await repository.get_persona(name)
    if persona is None:
        available = [item.name for item in await repository.list_personas()]
        known = ", ".join(available) if available else "none"
        return None, _text_result(
            f"No persona named '{name}'. Available personas: {known}.",
            is_error=True,
        )

    missing: list[str] = []
    for skill_name in persona.skills_json or []:
        try:
            if skill_registry.resolve(skill_name) is None:
                missing.append(skill_name)
        except FileNotFoundError:
            missing.append(skill_name)
    if missing:
        return None, _text_result(
            f"Persona '{name}' names {'skills' if len(missing) > 1 else 'a skill'} "
            f"that no longer exist: {', '.join(missing)}. "
            "Fix the persona before starting a subagent from it.",
            is_error=True,
        )

    return resolve_persona(parent_session, persona), None


def make_spawn_subagent_handler(
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    job: Any,
    skill_registry: SkillRegistry,
    schedule_child_fn: Callable[[str], Any] | None = None,
    monitor_timeout_seconds: float = DEFAULT_SUBAGENT_WAIT_TIMEOUT_SECONDS,
    monitor_poll_interval_seconds: float = DEFAULT_SUBAGENT_WAIT_POLL_INTERVAL_SECONDS,
) -> BuiltinHandler:
    """Return a spawn_subagent handler bound to the current parent job context.

    The handler returns immediately after enqueuing the child job. A detached
    background task monitors the child and appends subagent_completed /
    subagent_failed to the parent job when the child reaches a terminal state.

    An optional ``persona`` argument (falling back to the session's default) is
    resolved and CAPTURED here: the resolved configuration becomes the child's own
    model-config row, skill rows, and metadata snapshot, so nothing at child run
    time reads the persona table again and editing or deleting the persona cannot
    change a child that has already been started.

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

        parent_session = await repository.get_session(session_id)
        if parent_session is None:
            return _text_result("Parent session not found.", is_error=True)

        requested_persona = str(arguments.get("persona") or "").strip()
        persona, persona_error = await _resolve_spawn_persona(
            repository=repository,
            skill_registry=skill_registry,
            parent_session=parent_session,
            requested_name=requested_persona,
        )
        if persona_error is not None:
            return persona_error

        child_metadata: dict[str, Any] = {}
        event_payload_extra: dict[str, Any] | None = None
        if persona is not None:
            child_metadata[SESSION_PERSONA_KEY] = persona.as_snapshot()
            event_payload_extra = {"persona": persona.name}

        return await _launch_child_agent(
            repository=repository,
            live_event_bus=live_event_bus,
            session_id=session_id,
            job_id=job_id,
            parent_session=parent_session,
            prompt=prompt,
            # No caller-supplied name: a spawn's own truncated prompt is exactly
            # the unreadable label DRA-21 removed, so the child is named for us.
            name=None,
            child_metadata=child_metadata,
            model_config=persona,
            skills=None if persona is None else persona.skills,
            schedule_child_fn=schedule_child_fn,
            monitor=monitor,
            event_payload_extra=event_payload_extra,
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
        orchestrated = is_orchestrated(parent_session)

        # A seat in an orchestrated game is a durable agent: the session created
        # for it the first time it plays is the session it plays every later round
        # on, so its own prior turns replay into each invocation. In chat mode the
        # pre-orchestration behaviour is kept exactly — a memoryless child that is
        # terminated when its job ends.
        existing_child_session = None
        if orchestrated and resolved.agent_session_id:
            existing_child_session = await repository.get_session(
                resolved.agent_session_id
            )
            if existing_child_session is None:
                logger.warning(
                    "Seat %s of session %s pointed at missing session %s; "
                    "creating a fresh one",
                    player_id,
                    session_id,
                    resolved.agent_session_id,
                )

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

        skills: list[str] | None = resolved.skills
        model_config: Any = resolved
        if orchestrated and resolved.persona and existing_child_session is None:
            # The seat's persona is resolved and snapshotted once, when the seat's
            # session is created. Nothing re-reads the persona table afterwards, so
            # editing it mid-game cannot change a seat that is already playing.
            persona_row = await repository.get_persona(resolved.persona)
            if persona_row is None:
                return _text_result(
                    f"Seat '{player_id}' names persona '{resolved.persona}', which "
                    "no longer exists. Ask the user to reconfigure the seat.",
                    is_error=True,
                )
            persona = resolve_persona(parent_session, persona_row)
            child_metadata[SESSION_PERSONA_KEY] = persona.as_snapshot()
            # The seat's own provider/model still wins: a persona describes how a
            # seat thinks, and the seat's configuration says what it thinks with.
            if not (resolved.provider_id and resolved.model_name):
                model_config = persona
            if player_config.skills_json is None and persona.skills is not None:
                skills = persona.skills

        async def record_seat_session(child_session_id: str) -> None:
            recorded = await repository.set_player_agent_session(
                session_id, player_id, child_session_id
            )
            if not recorded:
                logger.warning(
                    "Seat %s of session %s already had a session recorded; "
                    "session %s will not be reused",
                    player_id,
                    session_id,
                    child_session_id,
                )

        return await _launch_child_agent(
            repository=repository,
            live_event_bus=live_event_bus,
            session_id=session_id,
            job_id=job_id,
            parent_session=parent_session,
            prompt=prompt,
            name=name,
            child_metadata=child_metadata,
            model_config=model_config,
            skills=skills,
            schedule_child_fn=schedule_child_fn,
            monitor=monitor,
            event_payload_extra={"player_id": player_id},
            multi_turn_memory=orchestrated,
            existing_child_session=existing_child_session,
            on_child_session_created=(record_seat_session if orchestrated else None),
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
            seat = await _child_seat_id(repository, child_job_id)
            if seat is not None:
                # A player seat's words reach the orchestrator only inside this
                # envelope: seat id and status as fields the server sets, the
                # seat's own text in one delimited block labelled untrusted. See
                # ``wrap_player_report``.
                return _text_result(
                    wrap_player_report(
                        player_id=seat,
                        job_status="completed",
                        text=outcome.text,
                    )
                )
            return _text_result(outcome.text or "Subagent completed.")
        return _text_result(
            describe_child_outcome(child_job_id, outcome), is_error=True
        )

    return handle


async def _child_seat_id(repository: Repository, child_job_id: str) -> str | None:
    """The seat a finished child was playing, or ``None`` if it held no seat.

    Read from the child *session's* metadata, which the orchestrator wrote when the
    seat was created and which no tool available to a player agent can change. That
    is what makes the seat id in a report envelope unforgeable by the seat.
    """
    try:
        child_job = await repository.get_job(child_job_id)
        if child_job is None:
            return None
        child_session = await repository.get_session(child_job.session_id)
        if child_session is None:
            return None
        return session_player_id(child_session)
    except Exception:
        logger.exception("Failed to resolve the seat for child job %s", child_job_id)
        return None


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
        durable_event_id = await repository.append_event(
            job_id, session_id, "subagent_failed", payload
        )
        await live_event_bus.publish(
            job_id, "subagent_failed", payload, durable_event_id=durable_event_id
        )
    except Exception:
        logger.exception(
            "Failed to record the abandoned wait for child job %s on parent job %s",
            child_job_id,
            job_id,
        )


DEFAULT_ASK_USER_TIMEOUT_SECONDS = 600.0
DEFAULT_ASK_USER_POLL_INTERVAL_SECONDS = 2.0

MAX_ASK_USER_CHOICES = 8
MAX_ASK_USER_QUESTION_LENGTH = 2000
MAX_ASK_USER_LABEL_LENGTH = 200
MAX_ASK_USER_VALUE_LENGTH = 200
MAX_ASK_USER_DESCRIPTION_LENGTH = 500


@dataclass(frozen=True)
class AskUserChoices:
    """A validated question, or the reason the model's arguments were rejected."""

    error: str | None = None
    question: str = ""
    choices: tuple[dict[str, str], ...] = ()
    allow_free_text: bool = False


def _validate_choice(index: int, raw: Any) -> tuple[str | None, dict[str, str]]:
    """Validate one choice, returning its normalized form or a reason to reject."""
    position = f"choices[{index}]"
    if not isinstance(raw, dict):
        return f"{position} must be an object with 'label' and 'value'.", {}

    normalized: dict[str, str] = {}
    for field, limit in (
        ("label", MAX_ASK_USER_LABEL_LENGTH),
        ("value", MAX_ASK_USER_VALUE_LENGTH),
    ):
        raw_field = raw.get(field)
        if not isinstance(raw_field, str) or not raw_field.strip():
            return f"{position}.{field} must be a non-empty string.", {}
        if len(raw_field) > limit:
            return f"{position}.{field} must be at most {limit} characters.", {}
        normalized[field] = raw_field.strip()

    description = raw.get("description")
    if description is not None:
        if not isinstance(description, str):
            return f"{position}.description must be a string when present.", {}
        if len(description) > MAX_ASK_USER_DESCRIPTION_LENGTH:
            return (
                f"{position}.description must be at most "
                f"{MAX_ASK_USER_DESCRIPTION_LENGTH} characters.",
                {},
            )
        stripped = description.strip()
        if stripped:
            normalized["description"] = stripped

    return None, normalized


def validate_ask_user_arguments(arguments: dict[str, Any]) -> AskUserChoices:
    """Validate an ask_user call before any question is recorded.

    A malformed question is the model's mistake to correct, not a failure of the
    run, so every rejection names the offending field. Nothing is written until
    the whole argument set is known to be good.
    """
    question = arguments.get("question")
    if not isinstance(question, str) or not question.strip():
        return AskUserChoices(error="question must be a non-empty string.")
    if len(question) > MAX_ASK_USER_QUESTION_LENGTH:
        return AskUserChoices(
            error=(
                "question must be at most "
                f"{MAX_ASK_USER_QUESTION_LENGTH} characters."
            )
        )

    raw_choices = arguments.get("choices")
    if not isinstance(raw_choices, list) or not raw_choices:
        return AskUserChoices(
            error="choices must be a non-empty array of {label, value} objects."
        )
    if len(raw_choices) > MAX_ASK_USER_CHOICES:
        return AskUserChoices(
            error=f"choices must contain at most {MAX_ASK_USER_CHOICES} entries."
        )

    normalized: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for index, raw in enumerate(raw_choices):
        error, choice = _validate_choice(index, raw)
        if error is not None:
            return AskUserChoices(error=error)
        # Duplicate values would make an answer ambiguous: the endpoint matches
        # an answer to a choice by value, so two choices sharing one cannot be
        # told apart.
        if choice["value"] in seen_values:
            return AskUserChoices(
                error=(
                    f"choices[{index}].value duplicates an earlier choice; "
                    "every value must be unique."
                )
            )
        seen_values.add(choice["value"])
        normalized.append(choice)

    allow_free_text = arguments.get("allow_free_text", False)
    if not isinstance(allow_free_text, bool):
        return AskUserChoices(error="allow_free_text must be true or false.")

    return AskUserChoices(
        question=question.strip(),
        choices=tuple(normalized),
        allow_free_text=allow_free_text,
    )


@dataclass(frozen=True)
class QuestionOutcome:
    """How a question ended, as far as the waiting run could observe.

    ``kind`` is ``answered`` when the user answered, ``timeout`` when the wait
    budget ran out, ``cancelled`` when the job's cancellation was requested,
    ``missing`` when the question row is gone (its session was deleted), or the
    reason recorded by whoever else closed it.
    """

    kind: str
    question: Any | None = None


async def resolve_question_outcome(
    *,
    repository: Repository,
    question_id: str,
    timeout_seconds: float = DEFAULT_ASK_USER_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_ASK_USER_POLL_INTERVAL_SECONDS,
    abandon_when: Callable[[], Awaitable[bool]] | None = None,
) -> QuestionOutcome:
    """Wait for the user to answer, bounded by an absolute deadline.

    The stored question is the only authority. Unlike a subagent wait, this one
    does not consume the live event bus: the answer is recorded by an HTTP
    request that may land on a different replica, and subscribing to this job's
    own stream would replay the run's entire event history back at it. A short
    poll interval is cheaper than that, and the user never perceives it — the
    browser shows the answer from its own response, not from the run resuming.

    The wait always ends, and the question is always closed before the run stops
    waiting on it, so a click arriving afterwards is refused rather than recorded
    against a question nobody is reading.
    """
    deadline = time.monotonic() + timeout_seconds

    while True:
        question = await repository.get_job_question(question_id)
        if question is None:
            return QuestionOutcome(kind="missing")
        if question.status == QUESTION_STATUS_ANSWERED:
            return QuestionOutcome(kind="answered", question=question)
        if question.status == QUESTION_STATUS_CLOSED:
            return QuestionOutcome(
                kind=question.closed_reason or "closed", question=question
            )

        if abandon_when is not None and await abandon_when():
            return await _close_or_take_late_answer(
                repository=repository, question_id=question_id, reason="cancelled"
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning(
                "Gave up after %.0fs waiting for an answer to question %s",
                timeout_seconds,
                question_id,
            )
            return await _close_or_take_late_answer(
                repository=repository, question_id=question_id, reason="timeout"
            )
        await asyncio.sleep(min(poll_interval_seconds, remaining))


async def _close_or_take_late_answer(
    *, repository: Repository, question_id: str, reason: str
) -> QuestionOutcome:
    """Close a question, unless an answer won the transition first.

    Closing is a conditional update, so it reports whether it actually happened.
    Losing that race means the user answered in the same instant the wait gave
    up, and their answer is the better outcome to return.
    """
    if await repository.close_job_question(question_id, reason=reason) is not None:
        return QuestionOutcome(kind=reason)
    question = await repository.get_job_question(question_id)
    if question is not None and question.status == QUESTION_STATUS_ANSWERED:
        return QuestionOutcome(kind="answered", question=question)
    return QuestionOutcome(kind=reason, question=question)


def describe_question_outcome(outcome: QuestionOutcome, timeout_seconds: float) -> str:
    """Render an unanswered outcome as one line the agent can act on."""
    if outcome.kind == "timeout":
        return (
            f"Nobody answered within {timeout_seconds:.0f}s. Continue using your "
            "own best judgement, or report that you are blocked and why. Do not "
            "ask this question again immediately."
        )
    if outcome.kind == "cancelled":
        return "Stopped waiting for an answer because this job was cancelled."
    if outcome.kind == "missing":
        return (
            "The question could not be found any more, so no answer can arrive. "
            "Continue without it or report that you are blocked."
        )
    return (
        f"The question stopped awaiting an answer ({outcome.kind}). Continue "
        "without it or report that you are blocked."
    )


def make_ask_user_handler(
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    job: Any,
    timeout_seconds: float = DEFAULT_ASK_USER_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_ASK_USER_POLL_INTERVAL_SECONDS,
) -> BuiltinHandler:
    """Return an ask_user handler that blocks until the user answers.

    The wait happens inside the tool call because a job cannot suspend, and the
    answer comes back as an ordinary tool result so it re-enters the model's
    context through the same message history every other tool result uses.
    """

    async def handle(arguments: dict[str, Any]) -> dict[str, Any]:
        if not is_master_job(job):
            return _text_result(
                "ask_user may only be called from a top-level (master) job — a "
                "subagent has no user attached to it.",
                is_error=True,
            )

        validated = validate_ask_user_arguments(arguments)
        if validated.error is not None:
            return _text_result(validated.error, is_error=True)

        choices = [dict(choice) for choice in validated.choices]
        question = await repository.create_job_question(
            job_id,
            session_id,
            question=validated.question,
            choices=choices,
            allow_free_text=validated.allow_free_text,
        )
        payload = {
            "question_id": question.id,
            "question": validated.question,
            "choices": choices,
            "allow_free_text": validated.allow_free_text,
        }
        durable_event_id = await repository.append_event(
            job_id, session_id, "user_question", payload
        )
        await live_event_bus.publish(
            job_id, "user_question", payload, durable_event_id=durable_event_id
        )

        async def job_was_cancelled() -> bool:
            if not job_id:
                return False
            return await repository.get_job_cancellation_requested(job_id)

        outcome = await resolve_question_outcome(
            repository=repository,
            question_id=question.id,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            abandon_when=job_was_cancelled,
        )

        if outcome.kind == "answered":
            answered = outcome.question
            assert answered is not None
            if answered.answer_source == "free_text":
                return _text_result(
                    f"The user answered in their own words: {answered.answer_text}"
                )
            return _text_result(
                f'The user chose "{answered.answer_label}" '
                f'(value: "{answered.answer_value}").'
            )

        await _announce_question_closed(
            repository=repository,
            live_event_bus=live_event_bus,
            session_id=session_id,
            job_id=job_id,
            question_id=question.id,
            reason=outcome.kind,
            waited_seconds=timeout_seconds,
        )
        # A timeout is a normal outcome, not a transient failure: marking it an
        # error invites the model to retry the tool straight away, which asks the
        # same unanswered question again.
        return _text_result(
            describe_question_outcome(outcome, timeout_seconds),
            is_error=outcome.kind in ("cancelled", "missing"),
        )

    return handle


async def _announce_question_closed(
    *,
    repository: Repository,
    live_event_bus: LiveEventBus,
    session_id: str,
    job_id: str,
    question_id: str,
    reason: str,
    waited_seconds: float,
) -> None:
    """Record on the job's timeline that a question stopped awaiting an answer."""
    if not job_id or not session_id:
        return
    payload = {
        "question_id": question_id,
        "reason": reason,
        "waited_seconds": waited_seconds,
    }
    try:
        durable_event_id = await repository.append_event(
            job_id, session_id, "user_question_closed", payload
        )
        await live_event_bus.publish(
            job_id,
            "user_question_closed",
            payload,
            durable_event_id=durable_event_id,
        )
    except Exception:
        logger.exception(
            "Failed to record the closure of question %s on job %s",
            question_id,
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
    ask_user_timeout_seconds: float = DEFAULT_ASK_USER_TIMEOUT_SECONDS,
    ask_user_poll_interval_seconds: float = DEFAULT_ASK_USER_POLL_INTERVAL_SECONDS,
) -> BuiltinToolRegistry:
    """Build a per-job BuiltinToolRegistry with all handlers bound to job context.

    schedule_child_fn: optional async callable(child_job_id) called concurrently
    after enqueueing a child job, to avoid single-worker deadlock.

    subagent_wait_timeout_seconds / subagent_wait_poll_interval_seconds: bound
    how long the parent will wait on a child and how often it re-reads the
    child's persisted status while waiting.

    ask_user_timeout_seconds / ask_user_poll_interval_seconds: bound how long the
    run will wait on a human and how often it re-reads the stored question.

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
                    "the child runs concurrently. Spawn multiple subagents before waiting for any. "
                    "Optionally pass `persona` to start the child from a configured persona, which "
                    "gives it that persona's instructions, skills, and (possibly narrower) tool "
                    "access instead of a copy of yours. Omit `persona` to give the child your own "
                    "configuration. Only the personas listed in your system prompt exist."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "prompt": {
                            "type": "string",
                            "description": "The prompt to send to the child agent.",
                        },
                        "persona": {
                            "type": "string",
                            "description": (
                                "Optional. The name of a configured persona to start "
                                "the child from, as listed in your system prompt. "
                                "Omit to give the child your own configuration."
                            ),
                        },
                    },
                    "required": ["prompt"],
                },
                handler=make_spawn_subagent_handler(
                    repository=repository,
                    live_event_bus=live_event_bus,
                    session_id=session_id,
                    job_id=job_id,
                    job=job,
                    skill_registry=skill_registry,
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

        registry.register(
            BuiltinToolDefinition(
                name="ask_user",
                description=(
                    "Ask the human a question and wait for their answer. "
                    "ONLY available to top-level jobs. "
                    "Use this instead of guessing whenever a decision is the "
                    "user's to make — which hero to play, which of two legal "
                    "plays they prefer, whether to continue — and instead of "
                    "ending your turn to ask in prose, which loses this run's "
                    "context. "
                    "Offer between 1 and 8 concrete choices; each needs a short "
                    "'label' the user will see on a button and a stable 'value' "
                    "you will get back. Set allow_free_text only when an answer "
                    "outside your list would actually be useful. "
                    "Blocks until the user answers or the wait is given up, and "
                    "always returns: if nobody answers you are told so and should "
                    "continue on your own judgement rather than asking again."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "The question to put to the user, in plain text."
                            ),
                        },
                        "choices": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": MAX_ASK_USER_CHOICES,
                            "description": (
                                "The answers to offer, one button each. Values "
                                "must be unique."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {
                                        "type": "string",
                                        "description": (
                                            "Short text shown on the button."
                                        ),
                                    },
                                    "value": {
                                        "type": "string",
                                        "description": (
                                            "Stable identifier returned to you "
                                            "when this choice is picked."
                                        ),
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": (
                                            "Optional one-line explanation shown "
                                            "under the label."
                                        ),
                                    },
                                },
                                "required": ["label", "value"],
                            },
                        },
                        "allow_free_text": {
                            "type": "boolean",
                            "description": (
                                "Also let the user type an answer of their own "
                                "instead of picking one of the choices."
                            ),
                        },
                    },
                    "required": ["question", "choices"],
                },
                handler=make_ask_user_handler(
                    repository=repository,
                    live_event_bus=live_event_bus,
                    session_id=session_id,
                    job_id=job_id,
                    job=job,
                    timeout_seconds=ask_user_timeout_seconds,
                    poll_interval_seconds=ask_user_poll_interval_seconds,
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
