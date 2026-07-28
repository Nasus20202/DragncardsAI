"""Agent personas: reusable configuration bundles a subagent can be started from.

A persona is the three things that make one agent behave differently from
another — a detailed system prompt, a skill selection, and a tool configuration —
stored under a name so it can be authored once and reused.

Two rules live here, and they are the reason this module is pure:

**Resolution happens once, at spawn time.** :func:`resolve_persona` merges a
stored persona over the spawning session, exactly the way
:func:`~agent_orchestrator.runtime.player_agents.resolve_player_agent_config`
merges a seat over its orchestrator. The result is materialised onto the child —
its model-config row, its skill rows, and a snapshot in its session metadata —
and nothing at child run time ever reads the persona table again. Editing or
deleting a persona therefore cannot change a subagent that is already running or
queued, which is what stops a subagent silently changing behaviour mid-game.

**A persona may narrow tool access, never widen it.** ``allowed_tools`` is an
allowlist applied by FILTERING the tools the child session already exposes, so it
is a subset operation: a name the child's catalogue does not contain simply does
not appear, and there is no field through which a persona could attach an MCP
server or reach a provider the deployment has not enabled. See
:func:`narrow_tool_definitions`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_orchestrator.runtime.skills import enabled_skill_assignments

# A persona name is a lowercase slug: it appears in an API path and an LLM types
# it into a tool argument, so it has to be short, unambiguous, and free of
# anything needing escaping.
PERSONA_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")

# A persona's prompt becomes part of a system prompt, so one persona must not be
# able to exhaust a context window or a request-body limit by itself.
MAX_PERSONA_PROMPT_CHARS = 8000
MAX_PERSONA_DESCRIPTION_CHARS = 2000
MAX_PERSONA_SKILLS = 32
MAX_PERSONA_ALLOWED_TOOLS = 128

# Session metadata key holding the persona snapshot captured when a child was
# started. Its presence is what makes a child session "a persona run".
SESSION_PERSONA_KEY = "agent_persona"


def is_valid_persona_name(name: str) -> bool:
    return bool(PERSONA_NAME_PATTERN.match(name))


@dataclass(frozen=True)
class ResolvedPersona:
    """What a subagent started from a persona will actually run with.

    Exposes ``provider_id`` / ``model_name`` / ``gateway_options`` /
    ``provider_options`` under the same names as
    :class:`~agent_orchestrator.runtime.player_agents.ResolvedPlayerAgentConfig`,
    so the shared child-launch path consumes either without knowing which it got.
    """

    name: str
    display_name: str | None
    system_prompt: str
    provider_id: str | None
    model_name: str | None
    gateway_options: dict[str, Any] = field(default_factory=dict)
    provider_options: dict[str, Any] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)
    # ``None`` means the persona narrows nothing.
    allowed_tools: list[str] | None = None

    def as_snapshot(self) -> dict[str, Any]:
        """The record written onto the child session at start time.

        Everything the child needs to run is here, so the child never reads the
        persona table — and everything a reader needs to interpret a past run is
        here too, so the record stays meaningful after the persona is deleted.
        """
        return {
            "name": self.name,
            "display_name": self.display_name,
            "system_prompt": self.system_prompt,
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "skills": list(self.skills),
            "allowed_tools": (
                None if self.allowed_tools is None else list(self.allowed_tools)
            ),
        }


def resolve_persona(parent_session: Any, persona: Any) -> ResolvedPersona:
    """Merge a stored persona over the session that is spawning the child.

    Unset provider/model inherit. Gateway and provider options are *overlaid* on
    the inherited ones rather than replacing them, so a persona can change one
    knob — reasoning effort, say — without restating the rest. Skills are
    all-or-nothing: a stored list (even an empty one) replaces the inherited set,
    while ``None`` inherits.
    """
    parent_model_config = getattr(parent_session, "model_config", None)
    parent_gateway = dict(getattr(parent_model_config, "gateway_options", None) or {})
    parent_provider_options = dict(
        getattr(parent_model_config, "provider_options", None) or {}
    )

    stored_skills = persona.skills_json
    if stored_skills is None:
        skills = [
            assignment.skill_name
            for assignment in enabled_skill_assignments(
                getattr(parent_session, "enabled_skills", [])
            )
        ]
    else:
        skills = list(stored_skills)

    allowed_tools = persona.allowed_tools_json
    return ResolvedPersona(
        name=persona.name,
        display_name=persona.display_name,
        system_prompt=persona.system_prompt or "",
        provider_id=persona.provider_id
        or getattr(parent_model_config, "provider_id", None),
        model_name=persona.model_name
        or getattr(parent_model_config, "model_name", None),
        gateway_options={**parent_gateway, **(persona.gateway_options or {})},
        provider_options={
            **parent_provider_options,
            **(persona.provider_options or {}),
        },
        skills=skills,
        allowed_tools=None if allowed_tools is None else list(allowed_tools),
    )


def session_persona_snapshot(session: Any) -> dict[str, Any] | None:
    """The persona snapshot captured on a session, or ``None`` if it has none."""
    metadata = getattr(session, "metadata_json", None) or {}
    snapshot = metadata.get(SESSION_PERSONA_KEY)
    return snapshot if isinstance(snapshot, dict) else None


def persona_prompt_from_snapshot(snapshot: dict[str, Any] | None) -> str | None:
    """The persona prompt to append to a subagent's system prompt, if any."""
    if not snapshot:
        return None
    prompt = snapshot.get("system_prompt")
    if not isinstance(prompt, str):
        return None
    trimmed = prompt.strip()
    return trimmed or None


def persona_allowed_tools_from_snapshot(
    snapshot: dict[str, Any] | None,
) -> list[str] | None:
    """The tool allowlist captured on a session, or ``None`` for no narrowing."""
    if not snapshot:
        return None
    allowed = snapshot.get("allowed_tools")
    if not isinstance(allowed, list):
        return None
    return [name for name in allowed if isinstance(name, str)]


def narrow_tool_definitions(
    tool_definitions: list[Any], allowed_tools: list[str] | None
) -> list[Any]:
    """Keep only the tool definitions a persona's allowlist permits.

    Filtering the *definitions* — rather than the list handed to the model — is
    what makes narrowing real: the same list produces both the offered tools and
    the dispatch mapping, so a tool a persona excluded is neither advertised nor
    callable by name.

    Because this can only ever remove entries, a persona cannot widen access. A
    name in the allowlist that the child does not expose has no effect at all.
    ``None`` narrows nothing.
    """
    if allowed_tools is None:
        return tool_definitions
    permitted = set(allowed_tools)
    return [
        definition
        for definition in tool_definitions
        if definition.exposed_name in permitted
    ]
