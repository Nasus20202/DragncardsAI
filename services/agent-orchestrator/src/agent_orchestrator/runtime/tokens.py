"""Token counting utilities for context window tracking."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_FALLBACK_ENCODING = "cl100k_base"  # GPT-4 / Claude-compatible approximation


def extract_tokens_from_response(raw: dict[str, Any]) -> int | None:
    """Extract total_tokens from an OpenAI-compatible usage field.

    Returns None if the field is absent.
    """
    usage = raw.get("usage")
    if isinstance(usage, dict):
        total = usage.get("total_tokens") or usage.get("output_tokens", 0) + usage.get(
            "input_tokens", 0
        )
        if total:
            return int(total)
    return None


def estimate_tokens_for_messages(messages: list[dict[str, Any]]) -> int:
    """Estimate token count for a messages list using tiktoken.

    Uses cl100k_base encoding as an approximation.  Logs a WARNING
    to indicate this is an estimate, not an authoritative count.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding(_FALLBACK_ENCODING)
        total = 0
        for message in messages:
            # Per-message overhead (role + separators): ~4 tokens
            total += 4
            content = message.get("content") or ""
            if isinstance(content, str):
                total += len(enc.encode(content))
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("text"):
                        total += len(enc.encode(part["text"]))
            tool_calls = message.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function", {})
                total += len(enc.encode(fn.get("name", "")))
                total += len(enc.encode(fn.get("arguments", "")))
        return total
    except Exception as exc:
        logger.warning(
            "tiktoken estimation failed (%s), using character heuristic", exc
        )
        # Final fallback: ~4 chars per token
        text = json.dumps(messages)
        return max(1, len(text) // 4)


def count_tokens_for_text(text: str) -> int:
    """Estimate token count for a plain text string."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding(_FALLBACK_ENCODING)
        return len(enc.encode(text))
    except Exception as exc:
        logger.warning(
            "tiktoken estimation failed (%s), using character heuristic", exc
        )
        return max(1, len(text) // 4)
