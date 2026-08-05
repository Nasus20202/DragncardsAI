"""The one place that decides whether a provider cut a response off.

Every vendor spells "I hit the output-token cap" differently, and the gateway
does not normalise all of them, so the vocabulary lives here rather than at the
call site. Adding a provider means adding a spelling to one set.

The set is deliberately closed. An unrecognised stop reason is **not**
truncation, which means an unknown value leaves behaviour exactly as it was
before automatic continuation existed. That asymmetry is the safety property:
the cost of a too-small set is that a user types "continue" as they do today,
and the cost of a too-broad set is paying a provider to push a model that had
finished its answer.
"""

from __future__ import annotations

# Lowercased, because vendors disagree about case: Gemini reports `MAX_TOKENS`
# where OpenAI reports `length`.
OUTPUT_TRUNCATION_STOP_REASONS: frozenset[str] = frozenset(
    {
        "length",  # OpenAI, and the OpenAI-compatible shape Bifrost emits
        "max_tokens",  # Anthropic, and Gemini/Vertex once lowercased
        "max_output_tokens",  # Vertex
        "max_completion_tokens",  # newer OpenAI-shaped APIs
        "model_length",  # gateways proxying self-hosted runtimes
        "token_limit",  # gateways proxying self-hosted runtimes
    }
)


def is_output_truncated(finish_reason: str | None) -> bool:
    """True only when the stop reason is a known way of saying "output cap"."""
    if not isinstance(finish_reason, str):
        return False
    return finish_reason.strip().lower() in OUTPUT_TRUNCATION_STOP_REASONS
