"""Unit tests for token counting utilities."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from agent_orchestrator.runtime.tokens import (
    count_tokens_for_text,
    estimate_tokens_for_messages,
    extract_tokens_from_response,
)


def test_extract_tokens_from_response_total_tokens():
    raw = {"usage": {"total_tokens": 512, "prompt_tokens": 300, "completion_tokens": 212}}
    assert extract_tokens_from_response(raw) == 512


def test_extract_tokens_from_response_input_output_fallback():
    raw = {"usage": {"input_tokens": 300, "output_tokens": 212}}
    assert extract_tokens_from_response(raw) == 512


def test_extract_tokens_from_response_missing_usage():
    assert extract_tokens_from_response({}) is None
    assert extract_tokens_from_response({"other": "field"}) is None


def test_estimate_tokens_for_messages_returns_positive():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"},
    ]
    count = estimate_tokens_for_messages(messages)
    assert count > 0


def test_estimate_tokens_for_messages_with_tool_calls():
    messages = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "tc1",
                    "type": "function",
                    "function": {"name": "draw_card", "arguments": '{"player": "player1"}'},
                }
            ],
        }
    ]
    count = estimate_tokens_for_messages(messages)
    assert count > 0


def test_count_tokens_for_text():
    count = count_tokens_for_text("Hello, world!")
    assert count > 0


def test_extract_tokens_handles_zero_total():
    # If total_tokens is 0, treat as absent
    raw = {"usage": {"total_tokens": 0}}
    assert extract_tokens_from_response(raw) is None
