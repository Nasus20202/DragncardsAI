from __future__ import annotations

from dataclasses import dataclass

from agent_orchestrator.integrations.mcp.client import StreamableHttpMcpClient


@dataclass
class Dumpable:
    value: str

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        assert mode == "json"
        return {"type": "text", "text": self.value}


def test_serialize_content_handles_supported_shapes():
    client = StreamableHttpMcpClient(timeout_seconds=12.5)

    assert client._serialize_content(Dumpable("ok")) == {"type": "text", "text": "ok"}
    assert client._serialize_content({"type": "text", "text": "raw"}) == {"type": "text", "text": "raw"}
    assert client._serialize_content([1, 2]) == {"type": "text", "text": "[1, 2]"}


def test_http_client_applies_headers_and_timeout():
    client = StreamableHttpMcpClient(timeout_seconds=12.5)
    http_client = client._http_client({"Authorization": "Bearer token"})
    try:
        assert http_client.headers["Authorization"] == "Bearer token"
        assert http_client.timeout.connect == 12.5
    finally:
        import asyncio

        asyncio.run(http_client.aclose())
