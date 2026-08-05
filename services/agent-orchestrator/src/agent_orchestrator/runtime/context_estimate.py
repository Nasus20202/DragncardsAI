"""The one place a session's context usage is turned into a number.

Two callers need to know how full a session's context is: the auto-compaction
trigger, which decides whether to summarize before sending the next request,
and the context metadata endpoint behind the dashboard's context widget. They
used to compute it separately — the trigger measured the replayed history
alone, the endpoint measured the system prompt, the replay and the MCP tool
definitions — so they reported different numbers for the same session and the
trigger fired against a figure the user never saw.

`estimate_request` is now the only function that adds context components
together. Both callers pass it the parts of the request they know about and
read the total off the result, so the two figures cannot drift apart again
without changing this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent_orchestrator.runtime.tokens import (
    estimate_tokens_for_messages,
    estimate_tokens_for_tools,
)


@dataclass(frozen=True)
class ContextEstimate:
    """The estimated size of one model request, split into its components.

    ``user_message`` is the current turn's prompt as the model will receive it,
    including any skill content the prompt loaded into itself. Only the trigger
    can know it: the metadata endpoint reports a session at rest, where the next
    prompt has not been typed yet, and leaves it at zero.
    """

    system_prompt: int
    tools: int
    replay: int
    user_message: int
    context_window_size: int

    @property
    def total(self) -> int:
        return self.system_prompt + self.tools + self.replay + self.user_message

    @property
    def fixed_cost(self) -> int:
        """The part of the request compaction cannot reduce.

        Compaction rewrites the replayed history and nothing else, so a session
        whose pressure lives here will not be helped by summarizing.
        """
        return self.system_prompt + self.tools + self.user_message

    @property
    def usage_ratio(self) -> float:
        if self.context_window_size <= 0:
            return 0.0
        return self.total / self.context_window_size

    @property
    def reported_usage_ratio(self) -> float:
        """`usage_ratio` clamped to 1.0 and rounded, for display and transport."""
        return round(min(self.usage_ratio, 1.0), 6)

    def as_breakdown(self) -> dict[str, int]:
        """The breakdown the context metadata endpoint publishes.

        The user message is deliberately absent: the endpoint reports a session
        at rest, so the field would always be zero there, and the trigger
        reports it on its log line instead.
        """
        return {
            "system_prompt": self.system_prompt,
            "replay": self.replay,
            "tools": self.tools,
        }

    def as_log_fields(self) -> str:
        return (
            f"system_prompt={self.system_prompt} tools={self.tools} "
            f"replay={self.replay} user_message={self.user_message} "
            f"total={self.total} window={self.context_window_size}"
        )

    def as_log_extra(self) -> dict[str, int]:
        """The same components as structured fields.

        The human-readable line is for a person reading logs; this is what a
        machine — a test asserting agreement with the metadata endpoint, or a
        log query comparing the two — should read, so neither is coupled to the
        other's wording.
        """
        return {
            "system_prompt": self.system_prompt,
            "tools": self.tools,
            "replay": self.replay,
            "user_message": self.user_message,
            "total": self.total,
            "context_window_size": self.context_window_size,
        }


def estimate_request(
    *,
    system_prompt: str,
    tools: list[dict[str, Any]],
    replay_messages: list[dict[str, Any]],
    user_message: str | None = None,
    context_window_size: int,
) -> ContextEstimate:
    """Estimate a model request from the four things it is made of.

    ``tools`` is the OpenAI-shaped list actually sent, built-in tools and MCP
    tools alike. ``replay_messages`` is the reconstructed prior history after
    the compaction checkpoint and the replay-window limits have been applied.
    """
    # An absent component costs nothing, including the per-message overhead:
    # a request with no system prompt does not carry an empty system message.
    return ContextEstimate(
        system_prompt=(
            estimate_tokens_for_messages([{"role": "system", "content": system_prompt}])
            if system_prompt
            else 0
        ),
        tools=estimate_tokens_for_tools(tools),
        replay=estimate_tokens_for_messages(replay_messages),
        user_message=(
            estimate_tokens_for_messages([{"role": "user", "content": user_message}])
            if user_message
            else 0
        ),
        context_window_size=context_window_size,
    )
