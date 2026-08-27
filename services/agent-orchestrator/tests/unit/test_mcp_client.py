from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from agent_orchestrator.integrations.mcp.client import McpClient, _tool_input_schema


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


def test_tool_input_schema_supports_old_and_new_mcp_sdk_fields():
    old_sdk_tool = SimpleNamespace(
        inputSchema={"type": "object", "properties": {"old": {}}}
    )
    new_sdk_tool = SimpleNamespace(
        input_schema={"type": "object", "properties": {"new": {}}}
    )
    missing_schema_tool = SimpleNamespace()

    assert _tool_input_schema(old_sdk_tool)["properties"] == {"old": {}}
    assert _tool_input_schema(new_sdk_tool)["properties"] == {"new": {}}
    assert _tool_input_schema(missing_schema_tool) == {
        "type": "object",
        "properties": {},
    }


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
