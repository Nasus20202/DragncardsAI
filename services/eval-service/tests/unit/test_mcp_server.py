"""The MCP surface a coding agent debugging this repo actually gets.

Asserted against the real app rather than by reading `EXCLUDED_ROUTES`, because
the exclusions are regexes matched against generated OpenAPI paths — a pattern
that quietly matches nothing looks identical to one that works.
"""

from __future__ import annotations

from eval_service import main as main_module
from eval_service import mcp_server
from eval_service.config import Settings
from eval_service.runtime.app import create_app


async def tools() -> list:
    app = create_app(settings=Settings(), start_worker=False)
    server = mcp_server.mount(app)
    return await server.list_tools()


async def tool_names() -> set[str]:
    return {tool.name for tool in await tools()}


def test_the_entrypoint_mounts_this_services_surface():
    assert main_module.mount_mcp is mcp_server.mount


def test_server_is_named_after_the_service():
    assert mcp_server.MCP_SERVER_NAME == "eval-service"


async def test_the_whole_evaluation_step_is_exposed():
    """Pick rounds, request a verdict, poll it, read it, cancel it."""
    names = await tool_names()

    assert {
        "list_game_rounds",
        "create_evaluation",
        "get_evaluation",
        "cancel_evaluation",
        "list_evaluations",
    } <= names


async def test_the_sse_stream_is_not_a_tool():
    """A tool call reads to completion; this response completes with the run."""
    assert "stream_evaluation" not in await tool_names()


async def test_bulk_deletion_is_not_a_tool_but_single_cleanup_is():
    """An agent must be able to clean up after itself without a blast radius."""
    names = await tool_names()

    assert "clear_evaluations" not in names
    assert "delete_evaluation" in names


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
