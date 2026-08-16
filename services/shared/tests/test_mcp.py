from __future__ import annotations

import pytest
from fastapi import FastAPI

from dragncards_common import mcp as shared_mcp
from dragncards_common.mcp import MCP_MOUNT_PATH, build_mcp_server, mount_mcp_server


def build_app() -> FastAPI:
    """An app shaped like the real services: probes, reads, writes, a stream."""
    app = FastAPI()

    @app.get("/health", operation_id="health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", operation_id="ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/capabilities", operation_id="capabilities")
    async def capabilities() -> dict[str, object]:
        return {"service": "svc", "version": "0.1.0", "features": []}

    @app.get("/games", operation_id="list_games")
    async def list_games() -> list[str]:
        return []

    @app.delete("/games/{game_id}", operation_id="delete_game")
    async def delete_game(game_id: str) -> dict[str, str]:
        return {"game_id": game_id}

    @app.get("/games/{game_id}/events", operation_id="list_events")
    async def list_events(game_id: str) -> list[str]:
        return []

    @app.post("/games/{game_id}/events", operation_id="backfill_event")
    async def backfill_event(game_id: str) -> dict[str, str]:
        return {"game_id": game_id}

    @app.get("/games/{game_id}/events/stream", operation_id="stream_events")
    async def stream_events(game_id: str) -> dict[str, str]:
        return {"game_id": game_id}

    return app


async def tool_names(server) -> set[str]:
    return {tool.name for tool in await server.list_tools()}


async def test_probes_are_never_exposed_as_tools():
    """Probes and own-state negotiation are noise in an LLM's tool list."""
    server = build_mcp_server(app=build_app(), name="svc")

    names = await tool_names(server)

    assert "health" not in names
    assert "ready" not in names
    assert "capabilities" not in names
    assert "list_games" in names


async def test_tools_are_named_after_the_endpoint_operation_ids():
    """The MCP surface is generated, so a tool is exactly its HTTP endpoint.

    This is what stops the MCP surface drifting from the HTTP API: there is no
    place to write a tool by hand, and a readable tool name comes from giving the
    route a readable `operation_id`.
    """
    server = build_mcp_server(app=build_app(), name="svc")

    assert await tool_names(server) == {
        "list_games",
        "delete_game",
        "list_events",
        "backfill_event",
        "stream_events",
    }


async def test_every_tool_refuses_arguments_the_endpoint_does_not_take():
    """The flattened tool schema carries `additionalProperties: false` at its root.

    FastMCP builds a tool's parameters by flattening the body's properties
    alongside the path parameters into a fresh object and never copies the body
    model's `additionalProperties` flag up to that root, so a strict client would
    otherwise accept — and the request director would silently drop — any
    argument the endpoint does not define. The bootstrap re-applies the flag, and
    this test pins that it reaches every tool in the surface.
    """
    server = build_mcp_server(app=build_app(), name="svc")

    tools = await server.list_tools()

    assert len(tools) > 0
    for tool in tools:
        assert tool.parameters.get("additionalProperties") is False, tool.name


async def test_a_path_regex_excludes_every_method_on_that_path():
    server = build_mcp_server(
        app=build_app(),
        name="svc",
        excluded_routes=[r"^/games/[^/]+/events$"],
    )

    names = await tool_names(server)

    assert "list_events" not in names
    assert "backfill_event" not in names


async def test_methods_can_be_excluded_one_at_a_time():
    """One path is often a safe read and an unsafe write.

    `history-service` has exactly this shape on `/games/{game_id}/events`: the
    GET is the transcript a debugging agent reads, the POST writes into the
    ordered event store.
    """
    server = build_mcp_server(
        app=build_app(),
        name="svc",
        excluded_routes=[(r"^/games/[^/]+/events$", ["POST"])],
    )

    names = await tool_names(server)

    assert "list_events" in names
    assert "backfill_event" not in names


async def test_excluding_a_route_from_mcp_leaves_the_http_endpoint_alone():
    app = build_app()
    mount_mcp_server(
        app=app,
        name="svc",
        excluded_routes=[(r"^/games/[^/]+$", ["DELETE"])],
    )

    http_routes = {
        (route.path, method)
        for route in app.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }

    assert ("/games/{game_id}", "DELETE") in http_routes


def test_mount_adds_the_transport_and_wraps_the_existing_lifespan():
    app = build_app()
    original_lifespan = app.router.lifespan_context

    mount_mcp_server(app=app, name="svc")

    assert any(getattr(r, "path", None) == MCP_MOUNT_PATH for r in app.routes)
    # The MCP session manager has its own lifespan; replacing rather than
    # wrapping the app's would leave the service's own startup unrun.
    assert app.router.lifespan_context is not original_lifespan


def test_mount_path_is_the_same_for_every_service():
    """Clients are configured by URL, so the path is not per-service policy."""
    assert MCP_MOUNT_PATH == "/mcp"


@pytest.mark.parametrize("probe", [r"^/health$", r"^/ready$", r"^/capabilities$"])
def test_probe_exclusions_are_not_overridable_by_a_caller(probe):
    """A service cannot opt back into exposing its probes or capabilities."""
    assert probe in shared_mcp.ALWAYS_EXCLUDED_ROUTES

    patterns = [rule.pattern for rule in shared_mcp._route_maps([])]

    assert probe in patterns
