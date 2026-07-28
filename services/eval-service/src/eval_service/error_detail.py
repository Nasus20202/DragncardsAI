"""Redaction and truncation of evaluation error detail.

Evaluation failures are surfaced to the dashboard verbatim so an operator can see
*why* a target failed, which means the text a gateway or HTTP client produced
must never carry a credential or a whole provider request body (prompts, recorded
game states). Every error string that reaches a target row passes through
:func:`sanitize_error_detail` at the repository boundary, so no call site can
forget to sanitize and no unsanitized text can be stored or streamed.
"""

from __future__ import annotations

import re

# Upper bound on stored/served error detail: long enough for a gateway message
# plus a short body excerpt, short enough that a provider echoing the whole
# request back cannot be persisted or pushed to a client.
MAX_ERROR_DETAIL_CHARS = 1000

REDACTED = "[REDACTED]"
_TRUNCATION_SUFFIX = "... (truncated)"

# Credential-bearing field/header names followed by their value. A separator of
# ``:`` or ``=`` is REQUIRED so prose ("the secret is wrong") is not mangled,
# while every realistic leak shape is covered: header (``Authorization: Bearer
# x``), JSON (``"api_key": "x"``), env/kv (``API_KEY=x``) and query (``?key=x``).
# An optional ``Bearer`` prefix is consumed as part of the value so the token
# after it is what gets replaced.
_SECRET_FIELD_RE = re.compile(r"""(?ix)
    \b(
        authorization | proxy-authorization
      | x-bf-api-key | x-api-key | x-goog-api-key
      | api[_-]?key | apikey
      | access[_-]?token | refresh[_-]?token | id[_-]?token | auth[_-]?token
      | client[_-]?secret | secret | password | passwd
    )
    (["']?\s*[:=]\s*["']?)
    (?:bearer\s+)?
    (?P<value>[^\s"',;)}\]]+)
    """)

# A bearer token with no preceding field name.
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[^\s\"',;)}\]]+")

# Bare provider key literals, which show up in gateway messages without any
# field name at all (Bifrost echoes the key it tried for a provider).
_KEY_LITERAL_RE = re.compile(
    r"(?i)\b(?:sk|sk-ant|sk-or-v1|sk-proj|xai|gsk|pplx|r8|hf|ghp|github_pat)"
    r"[-_][A-Za-z0-9_\-]{12,}"
)
_GOOGLE_KEY_RE = re.compile(r"\bAIza[A-Za-z0-9_\-]{10,}")


def _redact_field(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{REDACTED}"


def sanitize_error_detail(detail: str | None) -> str | None:
    """Redact credentials from ``detail`` and bound its length.

    Returns ``None`` unchanged (a target with no error), and an empty string
    unchanged. Redaction runs before truncation so a secret cannot survive by
    sitting past the cut.
    """
    if detail is None:
        return None
    text = str(detail)
    if not text:
        return text

    text = _SECRET_FIELD_RE.sub(_redact_field, text)
    text = _BEARER_RE.sub(f"Bearer {REDACTED}", text)
    text = _KEY_LITERAL_RE.sub(REDACTED, text)
    text = _GOOGLE_KEY_RE.sub(REDACTED, text)

    if len(text) > MAX_ERROR_DETAIL_CHARS:
        keep = MAX_ERROR_DETAIL_CHARS - len(_TRUNCATION_SUFFIX)
        text = text[:keep] + _TRUNCATION_SUFFIX
    return text
