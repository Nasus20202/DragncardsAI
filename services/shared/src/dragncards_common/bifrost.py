"""Shared Bifrost gateway error type and HTTP error mapping.

Both the agent-orchestrator and eval-service talk to the Bifrost LLM gateway and
translate its failures into the same typed :class:`BifrostError` with a stable
``code`` and a ``retryable`` flag. The error extraction and status/transport
mapping are identical across services and live here.
"""

from __future__ import annotations

import httpx


class BifrostError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def extract_error_message(response: httpx.Response) -> str:
    """Pull the most specific human-readable message out of a Bifrost error body."""
    try:
        payload = response.json()
    except ValueError:
        return f"Bifrost returned HTTP {response.status_code}"
    detail = payload.get("error") or payload.get("message") or payload
    if isinstance(detail, dict):
        detail = (
            detail.get("message") or detail.get("detail") or "Bifrost request failed"
        )
    return str(detail)


def gateway_error(response: httpx.Response) -> BifrostError:
    """Build a ``gateway_error`` for a >=400 Bifrost response.

    5xx and 429 are marked retryable; all other 4xx are treated as definitive.
    """
    return BifrostError(
        "gateway_error",
        extract_error_message(response),
        retryable=response.status_code >= 500 or response.status_code == 429,
    )


def transport_error(
    exc: httpx.HTTPError,
    *,
    timeout_message: str,
    network_message: str,
) -> BifrostError:
    """Map an httpx transport failure to a retryable ``timeout``/``network_error``."""
    if isinstance(exc, httpx.TimeoutException):
        return BifrostError("timeout", timeout_message, retryable=True)
    return BifrostError("network_error", network_message, retryable=True)
