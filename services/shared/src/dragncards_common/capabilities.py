"""Capability-negotiation payloads shared by the first-party Python services.

A client that wants to know what a server supports before it sends anything
asks ``GET /capabilities``. The answer is derived from the app's own OpenAPI
document, never from a hand-maintained list: every route the app serves appears
as ``verb:path``, so a route added later is advertised without anyone
remembering to add it, and a route removed stops being advertised. That is the
structural guard DRA-59 exists to provide — the omission class that produced
DRA-53 (a field sent to a server that predates it) cannot recur through a
forgotten list, because there is no list to forget.

The endpoint itself is deliberately excluded from the MCP surface by
``dragncards_common.mcp.ALWAYS_EXCLUDED_ROUTES``: it describes the server's own
state, like the health and readiness probes, and an agent gains nothing from a
tool that tells it about the server it is already talking to.
"""

from __future__ import annotations

from typing import Any

#: The HTTP verbs FastAPI documents on a path item. Path items may also carry a
#: non-method ``parameters`` key, which is why membership here is the filter.
HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def route_features(openapi: dict[str, Any]) -> list[str]:
    """Every documented route as ``verb:path``, sorted, each exactly once.

    ``openapi`` is the app's own ``openapi()`` document, so the list is derived
    from the route table the app actually serves rather than from a list a
    developer has to keep current.
    """
    return sorted(
        f"{method}:{path}"
        for path, path_item in openapi.get("paths", {}).items()
        for method in path_item
        if method in HTTP_METHODS
    )


def capabilities_payload(app: Any, service_name: str) -> dict[str, object]:
    """The ``GET /capabilities`` response for ``app``.

    ``version`` is the app's own version string — the one the FastAPI
    constructor declares and the OpenAPI document's ``info.version`` echoes —
    so the payload cannot describe a different version than the document the
    structural tests derive the feature list from.
    """
    openapi = app.openapi()
    return {
        "service": service_name,
        "version": app.version,
        "features": route_features(openapi),
    }
