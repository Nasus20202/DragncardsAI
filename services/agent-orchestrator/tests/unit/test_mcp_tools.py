from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_orchestrator.integrations.mcp.client import McpToolDefinition
from agent_orchestrator.integrations.mcp.tools import (
    McpToolCatalog,
    normalize_mcp_server_url,
    safe_tool_name,
)


class FakeMcpClient:
    def __init__(self):
        self.calls = []

    async def list_tools(self, server_url, headers=None):
        self.calls.append(("list_tools", server_url, headers))
        return [
            McpToolDefinition(
                name="next step",
                description="Advance the game",
                input_schema={"type": "object", "properties": {"count": {"type": "integer"}}},
            )
        ]

    async def call_tool(self, server_url, tool_name, arguments, headers=None):
        self.calls.append(("call_tool", server_url, tool_name, arguments, headers))
        return {"is_error": False, "content": [{"type": "text", "text": "ok"}]}


def test_normalize_mcp_server_url_only_for_streamable_http():
    assert normalize_mcp_server_url("http://game-service/mcp", "streamable-http") == "http://game-service/mcp/"
    assert normalize_mcp_server_url("http://game-service/mcp", "sse") == "http://game-service/mcp"


def test_safe_tool_name_replaces_unsupported_characters():
    assert safe_tool_name("game service/next step") == "game_service_next_step"


@pytest.mark.asyncio
async def test_mcp_tool_catalog_builds_and_calls_tools():
    client = FakeMcpClient()
    catalog = McpToolCatalog(client)
    assignment = SimpleNamespace(
        name="game-service",
        transport="streamable-http",
        server_url="http://game-service/mcp",
        headers_json={"Authorization": "Bearer token"},
    )

    tools = await catalog.list_session_tools([assignment])

    assert tools[0].exposed_name == "game-service_next_step"
    assert tools[0].server_url == "http://game-service/mcp/"
    assert catalog.as_openai_tools(tools)[0]["function"]["name"] == "game-service_next_step"
    assert catalog.as_mapping(tools)["game-service_next_step"].actual_name == "next step"

    result = await catalog.call_tool(tools[0], {"count": 1})

    assert result["is_error"] is False
    assert client.calls[0] == (
        "list_tools",
        "http://game-service/mcp/",
        {"Authorization": "Bearer token"},
    )
    assert client.calls[1] == (
        "call_tool",
        "http://game-service/mcp/",
        "next step",
        {"count": 1},
        {"Authorization": "Bearer token"},
    )
