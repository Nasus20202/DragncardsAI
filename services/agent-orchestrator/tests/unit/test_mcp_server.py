"""The MCP surface a coding agent debugging this repo actually gets.

This is the service's *outbound* surface — the one a coding agent calls. It is not
`agent_orchestrator.integrations.mcp`, which is the MCP client this service uses
to hand tools to the game-playing agent.

Asserted against the real app rather than by reading `EXCLUDED_ROUTES`, because
the exclusions are regexes matched against generated OpenAPI paths — a pattern
that quietly matches nothing looks identical to one that works.
"""

from __future__ import annotations

import jsonschema
import pytest

from agent_orchestrator import main as main_module
from agent_orchestrator import mcp_server
from agent_orchestrator.config import Settings
from agent_orchestrator.runtime.app import create_app


async def tools() -> list:
    server = mcp_server.mount(create_app(settings=Settings()))
    return await server.list_tools()


async def tool_names() -> set[str]:
    return {tool.name for tool in await tools()}


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
    # Own-state negotiation: a client asks the server over HTTP before it sends.
    assert "capabilities" not in names


async def test_every_tool_refuses_arguments_the_endpoint_does_not_take():
    """A tool's input schema forbids additional properties at the root.

    FastMCP flattens a body's properties alongside the path parameters into a
    fresh object and drops the body model's `additionalProperties` flag on the
    way, so without this the strict request bodies this service declares never
    reach a tool call and an unknown argument is dropped by FastMCP's request
    director with a log warning only.
    """
    for tool in await tools():
        assert tool.parameters.get("additionalProperties") is False, tool.name


async def test_a_hallucinated_tool_argument_is_refused_not_dropped():
    """A call with an unknown argument fails the served input schema.

    A strict client validates a generated call against the tool's inputSchema
    before sending it, so `additionalProperties: false` at the root makes the
    inference-time layer refuse `allowed_subagants` — the argument never reaches
    the request director that would otherwise drop it and report success. This
    exercises the exact schema that client sees, via the same JSON Schema
    validation it applies.
    """
    create_session = next(
        tool for tool in await tools() if tool.name == "create_session"
    )
    schema = create_session.parameters

    # A valid call — every field optional — still validates.
    jsonschema.validate({}, schema)

    # A hallucinated argument is refused, naming the offending key.
    with pytest.raises(jsonschema.ValidationError) as excinfo:
        jsonschema.validate({"allowed_subagants": ["nope"]}, schema)
    assert "allowed_subagants" in str(excinfo.value)
