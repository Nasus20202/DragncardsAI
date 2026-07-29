"""The MCP surface a coding agent debugging this repo actually gets.

This is the service's *outbound* surface — the one a coding agent calls. It is not
`agent_orchestrator.integrations.mcp`, which is the MCP client this service uses
to hand tools to the game-playing agent.

Asserted against the real app rather than by reading `EXCLUDED_ROUTES`, because
the exclusions are regexes matched against generated OpenAPI paths — a pattern
that quietly matches nothing looks identical to one that works.
"""

from __future__ import annotations

from agent_orchestrator import main as main_module
from agent_orchestrator import mcp_server
from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.app import create_app


async def tool_names() -> set[str]:
    server = mcp_server.mount(create_app(settings=Settings()))
    return {tool.name for tool in await server.list_tools()}


def test_the_entrypoint_mounts_this_services_surface():
    assert main_module.mount_mcp is mcp_server.mount


def test_server_is_named_after_the_service():
    assert mcp_server.MCP_SERVER_NAME == "agent-orchestrator"


async def test_starting_a_player_agent_is_fully_exposed():
    """Create a session, configure it, give it skills and tools, prompt it."""
    names = await tool_names()

    assert {
        "create_session",
        "set_session_model_config",
        "enable_session_skill",
        "add_session_mcp",
        "save_session_player",
        "submit_prompt",
    } <= names


async def test_reading_what_the_agent_did_is_fully_exposed():
    names = await tool_names()

    assert {
        "get_job",
        "get_job_status",
        "list_job_events",
        "list_session_jobs",
        "get_session_context",
        "list_session_tools",
    } <= names


async def test_the_sse_stream_is_not_a_tool():
    """A tool call reads to completion; an event stream never completes."""
    names = await tool_names()

    assert "stream_job_events" not in names
    # The paged read is the surface an agent should poll instead.
    assert "list_job_events" in names


async def test_deployment_global_registries_are_readable_but_not_writable():
    """An entry added here changes what every session in the deployment gets."""
    names = await tool_names()

    assert {"list_skill_registry", "list_mcp_registry"} <= names
    assert {
        "register_skill",
        "unregister_skill",
        "register_mcp",
        "unregister_mcp",
    }.isdisjoint(names)


async def test_personas_are_readable_but_not_authorable():
    names = await tool_names()

    assert {"list_personas", "get_persona"} <= names
    assert {"save_persona", "delete_persona"}.isdisjoint(names)


async def test_per_session_lifecycle_stays_available():
    """Excluding the global registries must not cost an agent its own cleanup."""
    names = await tool_names()

    assert {
        "terminate_session",
        "delete_session",
        "disable_session_skill",
        "remove_session_mcp",
    } <= names


async def test_probes_are_not_tools():
    names = await tool_names()

    assert "health" not in names
    assert "ready" not in names
