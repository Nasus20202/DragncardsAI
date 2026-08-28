from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from agent_orchestrator.integrations.mcp.client import McpClient


@dataclass
class Dumpable:
    value: str

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        assert mode == "json"
        return {"type": "text", "text": self.value}


def test_serialize_content_handles_supported_shapes():
    client = McpClient(timeout_seconds=12.5)

    assert client._serialize_content(Dumpable("ok")) == {"type": "text", "text": "ok"}
    assert client._serialize_content({"type": "text", "text": "raw"}) == {
        "type": "text",
        "text": "raw",
    }
    assert client._serialize_content([1, 2]) == {"type": "text", "text": "[1, 2]"}


def test_http_client_applies_headers_and_timeout():
    client = McpClient(timeout_seconds=12.5)
    http_client = client._http_client({"Authorization": "Bearer token"})
    try:
        assert http_client.headers["Authorization"] == "Bearer token"
        assert http_client.timeout.connect == 12.5
    finally:
        import asyncio

        asyncio.run(http_client.aclose())


def test_mcp_client_supports_both_transports():
    client = McpClient(timeout_seconds=30.0)
    assert "streamable-http" in ("streamable-http", "sse")
    assert "sse" in ("streamable-http", "sse")


def test_unpack_transport_streams_supports_pair_and_triplet_shapes():
    client = McpClient(timeout_seconds=30.0)
    read = object()
    write = object()
    metadata = object()

    assert client._unpack_transport_streams((read, write)) == (read, write, None)
    assert client._unpack_transport_streams((read, write, metadata)) == (
        read,
        write,
        metadata,
    )


def test_unpack_transport_streams_rejects_invalid_shapes():
    client = McpClient(timeout_seconds=30.0)

    with pytest.raises(ValueError, match="MCP transport must yield"):
        client._unpack_transport_streams((object(),))


@pytest.mark.asyncio
async def test_list_tools_uses_mcp_v2_input_schema(monkeypatch: pytest.MonkeyPatch):
    client = McpClient(timeout_seconds=30.0)
    tool = Tool(
        name="echo",
        description="Echo input",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[tool])

    @asynccontextmanager
    async def session(*_args, **_kwargs):
        yield Session()

    monkeypatch.setattr(client, "_session", session)

    tools = await client.list_tools("http://mcp.test", "streamable-http")

    assert tools[0].input_schema == tool.input_schema


@pytest.mark.asyncio
async def test_call_tool_uses_mcp_v2_is_error(monkeypatch: pytest.MonkeyPatch):
    client = McpClient(timeout_seconds=30.0)
    result = CallToolResult(
        content=[TextContent(type="text", text="ok")],
        is_error=False,
    )

    class Session:
        async def call_tool(self, name, arguments=None):
            assert name == "echo"
            assert arguments == {"text": "hello"}
            return result

    @asynccontextmanager
    async def session(*_args, **_kwargs):
        yield Session()

    monkeypatch.setattr(client, "_session", session)

    response = await client.call_tool(
        "http://mcp.test",
        "streamable-http",
        "echo",
        {"text": "hello"},
    )

    assert response["is_error"] is False
    assert response["content"][0]["text"] == "ok"
