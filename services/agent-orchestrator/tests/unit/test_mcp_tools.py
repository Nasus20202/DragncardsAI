from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_orchestrator.integrations.mcp.client import McpClientError, McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import (
    McpToolCatalog,
    normalize_mcp_server_url,
    safe_tool_name,
)


class FakeMcpClient:
    def __init__(self):
        self.calls = []

    async def list_tools(self, server_url, transport, headers=None):
        self.calls.append(("list_tools", server_url, transport, headers))
        return [
            McpToolDefinition(
                name="next step",
                description="Advance the game",
                input_schema={
                    "type": "object",
                    "properties": {"count": {"type": "integer"}},
                },
            )
        ]

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        self.calls.append(
            ("call_tool", server_url, transport, tool_name, arguments, headers)
        )
        return {"is_error": False, "content": [{"type": "text", "text": "ok"}]}


class FailingMcpClient(FakeMcpClient):
    async def list_tools(self, server_url, transport, headers=None):
        self.calls.append(("list_tools", server_url, transport, headers))
        if "bad" in server_url:
            raise McpClientError("connection failed")
        return await super().list_tools(server_url, transport, headers=headers)

    async def call_tool(
        self, server_url, transport, tool_name, arguments, headers=None
    ):
        self.calls.append(
            ("call_tool", server_url, transport, tool_name, arguments, headers)
        )
        if "bad" in server_url:
            raise McpClientError("connection failed")
        return await super().call_tool(
            server_url, transport, tool_name, arguments, headers=headers
        )


def test_normalize_mcp_server_url_only_for_streamable_http():
    assert (
        normalize_mcp_server_url("http://game-service/mcp", "streamable-http")
        == "http://game-service/mcp/"
    )
    assert (
        normalize_mcp_server_url("http://game-service/mcp", "sse")
        == "http://game-service/mcp"
    )


def test_safe_tool_name_replaces_unsupported_characters():
    assert safe_tool_name("game service/next step") == "game_service_next_step"


@pytest.mark.asyncio
async def test_mcp_tool_catalog_builds_and_calls_tools():
    client = FakeMcpClient()
    catalog = McpToolCatalog(client)
    mcp_registry = SimpleNamespace(
        name="game-service",
        transport="streamable-http",
        server_url="http://game-service/mcp",
        headers_json={"Authorization": "Bearer token"},
    )
    enabled_mcp = SimpleNamespace(
        mcp_name="game-service",
        enabled=True,
        mcp=mcp_registry,
    )

    tools = await catalog.list_session_tools([enabled_mcp], [mcp_registry])

    assert tools[0].exposed_name == "game-service_next_step"
    assert tools[0].server_url == "http://game-service/mcp/"
    assert (
        catalog.as_openai_tools(tools)[0]["function"]["name"]
        == "game-service_next_step"
    )
    assert (
        catalog.as_mapping(tools)["game-service_next_step"].actual_name == "next step"
    )

    result = await catalog.call_tool(tools[0], {"count": 1})

    assert result["is_error"] is False
    assert client.calls[0] == (
        "list_tools",
        "http://game-service/mcp/",
        "streamable-http",
        {"Authorization": "Bearer token"},
    )
    assert client.calls[1] == (
        "call_tool",
        "http://game-service/mcp/",
        "streamable-http",
        "next step",
        {"count": 1},
        {"Authorization": "Bearer token"},
    )


@pytest.mark.asyncio
async def test_mcp_tool_catalog_can_skip_unreachable_assignments_for_read_paths():
    client = FailingMcpClient()
    catalog = McpToolCatalog(client)
    mcp_registries = [
        SimpleNamespace(
            name="bad-service",
            transport="streamable-http",
            server_url="http://bad-service/mcp",
            headers_json={},
        ),
        SimpleNamespace(
            name="game-service",
            transport="streamable-http",
            server_url="http://game-service/mcp",
            headers_json={},
        ),
    ]
    enabled_mcps = [
        SimpleNamespace(
            mcp_name="bad-service",
            enabled=True,
            mcp=mcp_registries[0],
        ),
        SimpleNamespace(
            mcp_name="game-service",
            enabled=True,
            mcp=mcp_registries[1],
        ),
    ]

    tools = await catalog.list_session_tools(
        enabled_mcps, mcp_registries, ignore_failures=True
    )

    assert [tool.assignment_name for tool in tools] == ["game-service"]


@pytest.mark.asyncio
async def test_mcp_tool_catalog_can_return_error_result_for_unreachable_tool_call():
    client = FailingMcpClient()
    catalog = McpToolCatalog(client)
    tool = SimpleNamespace(
        exposed_name="bad-service_next_step",
        actual_name="next_step",
        assignment_name="bad-service",
        server_url="http://bad-service/mcp/",
        headers={},
        transport="streamable-http",
    )

    result = await catalog.call_tool(tool, {}, ignore_failures=True)

    assert result == {
        "is_error": True,
        "content": [
            {"type": "text", "text": "MCP tool call failed: connection failed"}
        ],
    }


def test_as_openai_tools_sanitizes_discriminated_union_schema():
    catalog = McpToolCatalog(FakeMcpClient())
    tools = catalog.as_openai_tools(
        [
            SimpleNamespace(
                exposed_name="game-service_execute_action",
                actual_name="execute_action",
                description="Execute a game action",
                parameters={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "action": {
                            "title": "Action",
                            "anyOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {"const": "next_step", "type": "string"}
                                    },
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "const": "draw_card",
                                            "type": "string",
                                        },
                                        "count": {"type": "integer"},
                                    },
                                },
                            ],
                            "discriminator": {
                                "propertyName": "type",
                                "mapping": {
                                    "next_step": "#/components/schemas/NextStepAction",
                                    "draw_card": "#/components/schemas/DrawCardAction",
                                },
                            },
                        },
                    },
                    "required": ["session_id", "action"],
                },
            )
        ]
    )

    parameters = tools[0]["function"]["parameters"]
    assert parameters["type"] == "object"
    assert parameters["required"] == ["session_id", "action"]
    assert parameters["properties"]["action"]["type"] == "object"
    assert parameters["properties"]["action"]["properties"]["type"] == {
        "type": "string",
        "enum": ["draw_card", "next_step"],
    }
    assert "anyOf" not in parameters["properties"]["action"]
    assert "discriminator" not in parameters["properties"]["action"]
    assert parameters["properties"]["action"]["additionalProperties"] is True


def test_as_openai_tools_collapse_nullable_union_fields():
    catalog = McpToolCatalog(FakeMcpClient())
    tools = catalog.as_openai_tools(
        [
            SimpleNamespace(
                exposed_name="demo_tool",
                actual_name="demo_tool",
                description="Demo tool",
                parameters={
                    "type": "object",
                    "properties": {
                        "player_n": {
                            "anyOf": [{"type": "string"}, {"type": "null"}],
                            "description": "Optional player identifier",
                        }
                    },
                },
            )
        ]
    )

    player_schema = tools[0]["function"]["parameters"]["properties"]["player_n"]
    assert player_schema == {
        "description": "Optional player identifier",
        "type": "string",
    }
