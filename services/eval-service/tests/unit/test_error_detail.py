from __future__ import annotations

import pytest

from eval_service.error_detail import (
    MAX_ERROR_DETAIL_CHARS,
    REDACTED,
    sanitize_error_detail,
)


def test_none_and_empty_pass_through():
    assert sanitize_error_detail(None) is None
    assert sanitize_error_detail("") == ""


def test_plain_message_is_left_intact():
    message = (
        'no supported key found with name "eval-judge" for provider: openrouter '
        "and model: anthropic/claude-sonnet-4"
    )
    assert sanitize_error_detail(message) == message


@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA",
        "sk-or-v1-0123456789abcdef0123456789",
        "sk-proj-ZZZZZZZZZZZZZZZZZZZZ",
        "xai-QQQQQQQQQQQQQQQQQQQQ",
        "gsk_WWWWWWWWWWWWWWWWWWWW",
        "AIzaSyABCDEFGHIJKLMNOPQ",
    ],
)
def test_bare_provider_key_literals_are_redacted(secret):
    sanitized = sanitize_error_detail(f"upstream rejected key {secret} for provider")
    assert secret not in sanitized
    assert REDACTED in sanitized


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Bearer supersecrettoken123",
        "headers={'authorization': 'Bearer supersecrettoken123'}",
        "Bearer supersecrettoken123",
        "x-bf-api-key: supersecrettoken123",
        '{"api_key": "supersecrettoken123"}',
        "API_KEY=supersecrettoken123",
        "https://gateway/v1?x-api-key=supersecrettoken123",
        'client_secret="supersecrettoken123"',
        "password: supersecrettoken123",
        '{"access_token":"supersecrettoken123"}',
    ],
)
def test_credential_fields_and_bearer_tokens_are_redacted(text):
    sanitized = sanitize_error_detail(text)
    assert "supersecrettoken123" not in sanitized
    assert REDACTED in sanitized


def test_detail_is_truncated_to_the_bound():
    # A provider echoing back the whole request body (prompt + recorded state)
    # must not be stored or streamed in full.
    sanitized = sanitize_error_detail("x" * 50_000)
    assert len(sanitized) == MAX_ERROR_DETAIL_CHARS
    assert sanitized.endswith("(truncated)")


def test_redaction_runs_before_truncation():
    # A secret sitting past the truncation point must still be redacted, not
    # merely cut off -- otherwise a slightly shorter body would leak it.
    detail = "y" * (MAX_ERROR_DETAIL_CHARS - 20) + " Bearer supersecrettoken123"
    sanitized = sanitize_error_detail(detail)
    assert "supersecrettoken123" not in sanitized
    assert len(sanitized) <= MAX_ERROR_DETAIL_CHARS
