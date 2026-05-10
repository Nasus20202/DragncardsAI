from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from agent_orchestrator.integrations.mcp.client import StreamableHttpMcpClient


@dataclass(frozen=True)
class SessionToolDefinition:
    exposed_name: str
    assignment_name: str
    transport: str
    server_url: str
    headers: dict[str, str]
    actual_name: str
    description: str | None
    parameters: dict[str, Any]


def normalize_mcp_server_url(server_url: str, transport: str) -> str:
    if transport == "streamable-http" and not server_url.endswith("/"):
        return f"{server_url}/"
    return server_url


def safe_tool_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value)


class McpToolCatalog:
    def __init__(self, mcp_client: StreamableHttpMcpClient):
        self._mcp_client = mcp_client

    async def list_session_tools(self, assignments: list[Any]) -> list[SessionToolDefinition]:
        tools: list[SessionToolDefinition] = []
        for assignment in assignments:
            normalized_url = normalize_mcp_server_url(assignment.server_url, assignment.transport)
            tool_definitions = await self._mcp_client.list_tools(
                normalized_url,
                headers=assignment.headers_json,
            )
            for definition in tool_definitions:
                tools.append(
                    SessionToolDefinition(
                        exposed_name=safe_tool_name(f"{assignment.name}_{definition.name}"),
                        assignment_name=assignment.name,
                        transport=assignment.transport,
                        server_url=normalized_url,
                        headers=dict(assignment.headers_json or {}),
                        actual_name=definition.name,
                        description=definition.description,
                        parameters=definition.input_schema,
                    )
                )
        return tools

    def as_openai_tools(self, definitions: list[SessionToolDefinition]) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.exposed_name,
                    "description": definition.description or f"MCP tool {definition.actual_name}",
                    "parameters": definition.parameters,
                },
            }
            for definition in definitions
        ]

    def as_mapping(self, definitions: list[SessionToolDefinition]) -> dict[str, SessionToolDefinition]:
        return {definition.exposed_name: definition for definition in definitions}

    async def call_tool(self, definition: SessionToolDefinition, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._mcp_client.call_tool(
            definition.server_url,
            definition.actual_name,
            arguments,
            headers=definition.headers,
        )
