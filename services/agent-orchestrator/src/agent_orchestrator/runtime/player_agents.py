"""Per-seat player agent configuration for orchestrated multi-player games.

Marvel Champions is cooperative: one to four players each control their own
hero against a villain run by the game rules. An orchestrated game runs one
agent per seat so each seat's play can be evaluated — and compared — on its own.

A seat's stored configuration states only what differs from the orchestrating
session; everything unset is inherited. :func:`resolve_player_agent_config` is
the single place that turns "the seat's row" plus "the parent session" into the
concrete provider, model, options, and skills a child agent will run with. It is
pure so the inheritance rules are directly testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Marvel Champions seats. The `player<N>` form matches DragnCards' own seat
# naming and eval-service's seat regex, so a move tagged here is attributable
# end to end without translation.
PLAYER_ID_PATTERN = re.compile(r"^player[1-4]$")
MAX_PLAYER_AGENTS = 4
MAX_PLAYER_SKILLS = 32

# Session metadata keys identifying a child session as a player seat.
SESSION_PLAYER_ID_KEY = "player_id"
SESSION_PLAYER_NAME_KEY = "player_display_name"
SESSION_ORCHESTRATOR_ID_KEY = "orchestrator_session_id"

# Reasoning travels inside gateway options under this key; the runtime,
# the dashboard, and eval-service's judge config all already read it there.
REASONING_KEY = "reasoning"

REASONING_EFFORTS = ("low", "medium", "high")


def is_valid_player_id(player_id: str) -> bool:
    return bool(PLAYER_ID_PATTERN.match(player_id))


def session_player_id(session: Any) -> str | None:
    """The seat a session represents, or ``None`` if it is not a player seat."""
    metadata = getattr(session, "metadata_json", None) or {}
    value = metadata.get(SESSION_PLAYER_ID_KEY)
    if isinstance(value, str) and is_valid_player_id(value):
        return value
    return None


def fold_reasoning(
    gateway_options: dict[str, Any],
    *,
    enabled: bool,
    effort: str | None,
    max_tokens: int | None,
) -> dict[str, Any]:
    """Return ``gateway_options`` with the reasoning block applied.

    Disabling removes the key entirely so the provider sees no reasoning
    request at all, which is what "reasoning off" has to mean.
    """
    resolved = dict(gateway_options)
    if not enabled:
        resolved.pop(REASONING_KEY, None)
        return resolved
    block: dict[str, Any] = {}
    if effort is not None:
        block["effort"] = effort
    if max_tokens is not None:
        block["max_tokens"] = max_tokens
    if not block:
        resolved.pop(REASONING_KEY, None)
        return resolved
    resolved[REASONING_KEY] = block
    return resolved


def unfold_reasoning(gateway_options: dict[str, Any] | None) -> dict[str, Any] | None:
    """The reasoning block stored in gateway options, if any."""
    if not gateway_options:
        return None
    block = gateway_options.get(REASONING_KEY)
    return dict(block) if isinstance(block, dict) else None


@dataclass(frozen=True)
class ResolvedPlayerAgentConfig:
    """What a player agent for one seat will actually run with."""

    player_id: str
    display_name: str | None
    provider_id: str | None
    model_name: str | None
    gateway_options: dict[str, Any] = field(default_factory=dict)
    provider_options: dict[str, Any] = field(default_factory=dict)
    skills: list[str] = field(default_factory=list)

    def as_summary(self) -> dict[str, Any]:
        """A compact roster entry for the orchestrator agent to read."""
        return {
            "player_id": self.player_id,
            "display_name": self.display_name,
            "provider_id": self.provider_id,
            "model_name": self.model_name,
            "reasoning": unfold_reasoning(self.gateway_options),
            "skills": list(self.skills),
        }


def resolve_player_agent_config(
    parent_session: Any, player_config: Any
) -> ResolvedPlayerAgentConfig:
    """Merge a seat's stored configuration over the orchestrator session's.

    Unset provider/model inherit. Gateway and provider options are *overlaid*
    on the inherited ones rather than replacing them, so a seat can change one
    knob without restating the rest. Skills are all-or-nothing: a stored list
    (even an empty one) replaces the inherited set, while ``None`` inherits.
    """
    parent_model_config = getattr(parent_session, "model_config", None)
    parent_provider = getattr(parent_model_config, "provider_id", None)
    parent_model = getattr(parent_model_config, "model_name", None)
    parent_gateway = dict(getattr(parent_model_config, "gateway_options", None) or {})
    parent_provider_options = dict(
        getattr(parent_model_config, "provider_options", None) or {}
    )

    gateway_options = {**parent_gateway, **(player_config.gateway_options or {})}
    provider_options = {
        **parent_provider_options,
        **(player_config.provider_options or {}),
    }

    stored_skills = player_config.skills_json
    if stored_skills is None:
        skills = [
            assignment.skill_name
            for assignment in getattr(parent_session, "enabled_skills", []) or []
            if assignment.enabled
        ]
    else:
        skills = list(stored_skills)

    return ResolvedPlayerAgentConfig(
        player_id=player_config.player_id,
        display_name=player_config.display_name,
        provider_id=player_config.provider_id or parent_provider,
        model_name=player_config.model_name or parent_model,
        gateway_options=gateway_options,
        provider_options=provider_options,
        skills=skills,
    )


def resolve_roster(
    parent_session: Any, player_configs: list[Any]
) -> list[ResolvedPlayerAgentConfig]:
    """Resolve every configured seat, ordered by seat id."""
    return [
        resolve_player_agent_config(parent_session, config)
        for config in sorted(player_configs, key=lambda item: item.player_id)
    ]
