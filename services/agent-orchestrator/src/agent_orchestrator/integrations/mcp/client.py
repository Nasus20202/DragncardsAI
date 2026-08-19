from __future__ import annotations

from contextlib import asynccontextmanager
import json
from dataclasses import dataclass
from typing import Any, Literal

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client


class McpClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpToolDefinition:
    name: str
    description: str | None
    input_schema: dict[str, Any]


McpTransport = Literal["streamable-http", "sse"]


class McpClient:
    def __init__(self, timeout_seconds: float = 30.0):
        self._timeout_seconds = timeout_seconds

    def _unpack_transport_streams(self, streams: Any) -> tuple[Any, Any, Any | None]:
        if isinstance(streams, tuple):
            if len(streams) == 2:
                return streams[0], streams[1], None
            if len(streams) >= 3:
                return streams[0], streams[1], streams[2]
        raise ValueError(
            "MCP transport must yield (read, write) or (read, write, metadata)"
        )

    async def list_tools(
        self,
        server_url: str,
        transport: McpTransport,
        headers: dict[str, str] | None = None,
    ) -> list[McpToolDefinition]:
        async with self._session(server_url, transport, headers) as session:
            result = await session.list_tools()
        return [
            McpToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=self._tool_input_schema(tool),
            )
            for tool in result.tools
        ]

    def _tool_input_schema(self, tool: Any) -> dict[str, Any]:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        return schema or {"type": "object", "properties": {}}

    async def call_tool(
        self,
        server_url: str,
        transport: McpTransport,
        tool_name: str,
        arguments: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with self._session(server_url, transport, headers) as session:
            result = await session.call_tool(tool_name, arguments=arguments)
        return {
            "is_error": result.isError,
            "content": [self._serialize_content(item) for item in result.content],
        }

    def _serialize_content(self, item: Any) -> dict[str, Any]:
        if hasattr(item, "model_dump"):
            return item.model_dump(mode="json")
        if isinstance(item, dict):
            return item
        return {"type": "text", "text": json.dumps(item)}

    def _http_client(self, headers: dict[str, str] | None) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=headers or {}, timeout=self._timeout_seconds)

    @asynccontextmanager
    async def _session(
        self,
        server_url: str,
        transport: McpTransport,
        headers: dict[str, str] | None = None,
    ):
        headers = headers or {}
        try:
            if transport == "sse":
                async with sse_client(server_url, headers=headers) as streams:
                    read, write, _ = self._unpack_transport_streams(streams)
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
            else:
                http_client = self._http_client(headers)
                try:
                    async with streamable_http_client(
                        server_url, http_client=http_client
                    ) as streams:
                        read, write, _ = self._unpack_transport_streams(streams)
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            yield session
                finally:
                    await http_client.aclose()
        except (
            Exception
        ) as exc:  # pragma: no cover - transport errors are surfaced to callers
            raise McpClientError(str(exc)) from exc


# Backwards compatibility alias
StreamableHttpMcpClient = McpClient
