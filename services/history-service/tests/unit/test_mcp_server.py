"""The MCP surface a coding agent debugging this repo actually gets.

Asserted against the real app rather than by reading `EXCLUDED_ROUTES`, because
the exclusions are regexes matched against generated OpenAPI paths — a pattern
that quietly matches nothing looks identical to one that works.
"""

from __future__ import annotations

from history_service import main as main_module
from history_service import mcp_server
from history_service.runtime.app import create_app


async def tools() -> list:
    server = mcp_server.mount(create_app(start_ingester=False))
    return await server.list_tools()


async def tool_names() -> set[str]:
    return {tool.name for tool in await tools()}


def test_the_entrypoint_mounts_this_services_surface():
    assert main_module.mount_mcp is mcp_server.mount


def test_server_is_named_after_the_service():
    assert mcp_server.MCP_SERVER_NAME == "history-service"


async def test_the_reads_a_debug_loop_needs_are_exposed():
    """Listing games, reading a game's events and its timeline, and restoring."""
    names = await tool_names()

    assert {
        "list_recorded_games",
        "list_game_events",
        "list_game_timeline",
        "list_game_snapshots",
        "restore_game",
    } <= names


async def test_irreversible_history_destruction_is_not_a_tool():
    """The event store is the only record of what an agent did."""
    assert "delete_game_history" not in await tool_names()


async def test_writes_into_the_ordered_event_store_are_not_tools():
    """A fabricated event corrupts the record while every read stays healthy."""
    names = await tool_names()

    assert "backfill_game_event" not in names
    assert "import_game_bundle" not in names


async def test_the_streaming_bundle_export_is_not_a_tool():
    """A whole recorded game would be buffered into the caller's context."""
    assert "export_game_bundle" not in await tool_names()


async def test_probes_are_not_tools():
    names = await tool_names()

    assert "health" not in names
    assert "ready" not in names
    # Own-state negotiation: a client asks the server over HTTP before it sends.
    assert "capabilities" not in names


async def test_every_tool_refuses_arguments_the_endpoint_does_not_take():
    """A tool's input schema forbids additional properties at the root.

    FastMCP flattens a body's properties alongside the path parameters into a
    fresh object and drops the body model's `additionalProperties` flag on the
    way, so without this an unknown tool argument is dropped by FastMCP's request
    director with a log warning only, and the model sees a successful call.
    """
    for tool in await tools():
        assert tool.parameters.get("additionalProperties") is False, tool.name
