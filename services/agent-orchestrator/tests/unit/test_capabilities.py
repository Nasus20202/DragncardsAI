"""`GET /capabilities` tells a client what this server supports, before the send.

The feature list is derived from the app's own OpenAPI document rather than
from a hand-maintained list, so a route added later is advertised without
anyone remembering to add it — the structural guard DRA-59 exists to provide.
This test mirrors `test_app_strict_request_bodies.py`: it reads the app's own
OpenAPI document and asserts the endpoint against it, so the endpoint cannot
drift from the route table the app actually serves.

A server old enough to lack the endpoint answers a client's `GET /capabilities`
with a 404, which is itself the signal that it predates the negotiation — the
asymmetry the ticket was filed for.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .app_test_support import build_test_app

#: The HTTP verbs FastAPI documents on a path item; path items may also carry a
#: non-method `parameters` key, which is why membership here is the filter.
HTTP_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
)


def _documented_features(openapi: dict) -> list[str]:
    return sorted(
        f"{method}:{path}"
        for path, path_item in openapi.get("paths", {}).items()
        for method in path_item
        if method in HTTP_METHODS
    )


@pytest.mark.asyncio
async def test_capabilities_are_derived_from_the_apps_own_route_table(
    tmp_path: Path,
):
    app, engine = await build_test_app(tmp_path)
    try:
        openapi = app.openapi()
        expected = _documented_features(openapi)
        # A guard on the guard: if the traversal found no routes, the equality
        # below would pass vacuously.
        assert len(expected) > 0

        with TestClient(app) as client:
            response = client.get("/capabilities")

        assert response.status_code == 200
        body = response.json()
        assert body["service"] == "agent-orchestrator"
        assert body["version"] == openapi["info"]["version"]
        # Every documented route exactly once, and nothing else.
        assert body["features"] == expected
        assert len(body["features"]) == len(set(body["features"]))
        assert "get:/capabilities" in body["features"]
    finally:
        await engine.dispose()
