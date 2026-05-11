from __future__ import annotations

from contextlib import asynccontextmanager
import json
from dataclasses import dataclass
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


class McpClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class McpToolDefinition:
    name: str
    description: str | None
    input_schema: dict[str, Any]


class StreamableHttpMcpClient:
    def __init__(self, timeout_seconds: float = 30.0):
        self._timeout_seconds = timeout_seconds

    async def list_tools(
        self, server_url: str, headers: dict[str, str] | None = None
    ) -> list[McpToolDefinition]:
        async with self._session(server_url, headers) as session:
            result = await session.list_tools()
        return [
            McpToolDefinition(
                name=tool.name,
                description=tool.description,
                input_schema=tool.inputSchema or {"type": "object", "properties": {}},
            )
            for tool in result.tools
        ]

    async def call_tool(
        self,
        server_url: str,
        tool_name: str,
        arguments: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        async with self._session(server_url, headers) as session:
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
    async def _session(self, server_url: str, headers: dict[str, str] | None = None):
        http_client = self._http_client(headers)
        try:
            async with streamable_http_client(server_url, http_client=http_client) as (
                read,
                write,
                _,
            ):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except (
            Exception
        ) as exc:  # pragma: no cover - transport errors are surfaced to callers
            raise McpClientError(str(exc)) from exc
        finally:
            await http_client.aclose()
