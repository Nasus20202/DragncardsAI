from __future__ import annotations

import pytest

from agent_orchestrator.runtime.truncation import is_output_truncated


@pytest.mark.parametrize(
    "finish_reason",
    [
        "length",
        "max_tokens",
        "MAX_TOKENS",
        "Max_Output_Tokens",
        "max_completion_tokens",
        "model_length",
        "token_limit",
        "  length  ",
    ],
)
def test_known_truncation_vocabularies_are_recognised(finish_reason: str) -> None:
    assert is_output_truncated(finish_reason)


@pytest.mark.parametrize(
    "finish_reason",
    [
        "stop",
        "end_turn",
        "tool_calls",
        "tool_use",
        "content_filter",
        "function_call",
        "",
        "   ",
        None,
    ],
)
def test_everything_else_is_not_truncation(finish_reason: str | None) -> None:
    """The safe asymmetry: an unknown reason means today's behaviour, unchanged."""
    assert not is_output_truncated(finish_reason)


def test_a_non_string_is_not_truncation() -> None:
    assert not is_output_truncated(42)  # type: ignore[arg-type]
