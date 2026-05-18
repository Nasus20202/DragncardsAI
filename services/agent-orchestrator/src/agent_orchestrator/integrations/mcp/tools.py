from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from agent_orchestrator.integrations.mcp.client import (
    McpClient,
    McpClientError,
)

logger = logging.getLogger(__name__)


def _sanitize_tool_parameters(schema: Any) -> dict[str, Any]:
    sanitized = _sanitize_schema_node(schema)
    if sanitized.get("type") != "object":
        return {"type": "object", "properties": {}}
    sanitized.setdefault("properties", {})
    return sanitized


def _sanitize_schema_node(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}

    description = schema.get("description")

    composed = schema.get("anyOf") or schema.get("oneOf")
    if isinstance(composed, list):
        collapsed = _collapse_nullable_union(composed)
        if collapsed is not None:
            if (
                isinstance(description, str)
                and description
                and "description" not in collapsed
            ):
                collapsed["description"] = description
            return collapsed
        merged = _merge_object_union(composed)
        if merged is not None:
            if (
                isinstance(description, str)
                and description
                and "description" not in merged
            ):
                merged["description"] = description
            return merged

    sanitized: dict[str, Any] = {}
    if isinstance(description, str) and description:
        sanitized["description"] = description

    schema_type = schema.get("type")
    if isinstance(schema_type, str) and schema_type != "null":
        sanitized["type"] = schema_type
    elif isinstance(schema_type, list):
        non_null_types = [
            value for value in schema_type if isinstance(value, str) and value != "null"
        ]
        if len(non_null_types) == 1:
            sanitized["type"] = non_null_types[0]
        elif non_null_types:
            sanitized["type"] = non_null_types

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and all(
        not isinstance(value, (dict, list)) for value in enum_values
    ):
        sanitized["enum"] = enum_values

    const_value = schema.get("const")
    if const_value is not None and not isinstance(const_value, (dict, list)):
        sanitized["const"] = const_value

    properties = schema.get("properties")
    if isinstance(properties, dict):
        sanitized["type"] = "object"
        sanitized["properties"] = {
            name: _sanitize_schema_node(value)
            for name, value in properties.items()
            if isinstance(name, str)
        }
        required = [
            name
            for name in schema.get("required") or []
            if isinstance(name, str) and name in sanitized["properties"]
        ]
        if required:
            sanitized["required"] = required

        additional_properties = schema.get("additionalProperties")
        if isinstance(additional_properties, bool):
            sanitized["additionalProperties"] = additional_properties
        elif isinstance(additional_properties, dict):
            sanitized_additional = _sanitize_schema_node(additional_properties)
            sanitized["additionalProperties"] = sanitized_additional or True

    items = schema.get("items")
    if isinstance(items, dict):
        sanitized["items"] = _sanitize_schema_node(items)
    elif items is True:
        sanitized["items"] = {}

    return sanitized


def _collapse_nullable_union(options: list[Any]) -> dict[str, Any] | None:
    non_null_options: list[dict[str, Any]] = []
    saw_null = False
    for option in options:
        if not isinstance(option, dict):
            return None
        option_type = option.get("type")
        if option_type == "null":
            saw_null = True
            continue
        if isinstance(option_type, list) and all(
            value == "null" for value in option_type
        ):
            saw_null = True
            continue
        non_null_options.append(option)

    if saw_null and len(non_null_options) == 1:
        return _sanitize_schema_node(non_null_options[0])
    return None


def _merge_object_union(options: list[Any]) -> dict[str, Any] | None:
    sanitized_options: list[dict[str, Any]] = []
    for option in options:
        if not isinstance(option, dict):
            return None
        sanitized_option = _sanitize_schema_node(option)
        if (
            not sanitized_option.get("properties")
            and sanitized_option.get("type") != "object"
        ):
            return None
        sanitized_options.append(sanitized_option)

    if not sanitized_options:
        return None

    variant_types: list[str] = []
    merged_properties: dict[str, Any] = {}
    for option in sanitized_options:
        properties = option.get("properties") or {}
        for name, value in properties.items():
            if name == "type":
                const_value = value.get("const") if isinstance(value, dict) else None
                if isinstance(const_value, str):
                    variant_types.append(const_value)
                continue
            merged_properties.setdefault(name, value)

    merged: dict[str, Any] = {
        "type": "object",
        "properties": merged_properties,
        "additionalProperties": True,
    }
    if variant_types:
        merged["properties"] = {
            "type": {"type": "string", "enum": sorted(set(variant_types))},
            **merged_properties,
        }
        merged["required"] = ["type"]
    return merged


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
    def __init__(self, mcp_client: McpClient):
        self._mcp_client = mcp_client

    async def list_session_tools(
        self,
        enabled_mcps: list[Any],
        all_registries: list[Any],
        *,
        ignore_failures: bool = False,
    ) -> list[SessionToolDefinition]:
        tools: list[SessionToolDefinition] = []
        registry_map = {r.name: r for r in all_registries}

        for enabled_mcp in enabled_mcps:
            if not enabled_mcp.enabled:
                continue
            registry = registry_map.get(enabled_mcp.mcp_name)
            if registry is None:
                continue

            normalized_url = normalize_mcp_server_url(
                registry.server_url, registry.transport
            )
            try:
                tool_definitions = await self._mcp_client.list_tools(
                    normalized_url,
                    registry.transport,
                    headers=registry.headers_json,
                )
            except McpClientError:
                if not ignore_failures:
                    raise
                logger.warning(
                    "Skipping unreachable MCP %s at %s during tool discovery",
                    registry.name,
                    normalized_url,
                    exc_info=True,
                )
                continue
            for definition in tool_definitions:
                tools.append(
                    SessionToolDefinition(
                        exposed_name=safe_tool_name(
                            f"{registry.name}_{definition.name}"
                        ),
                        assignment_name=registry.name,
                        transport=registry.transport,
                        server_url=normalized_url,
                        headers=dict(registry.headers_json or {}),
                        actual_name=definition.name,
                        description=definition.description,
                        parameters=definition.input_schema,
                    )
                )
        return tools

    def as_openai_tools(
        self, definitions: list[SessionToolDefinition]
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.exposed_name,
                    "description": definition.description
                    or f"MCP tool {definition.actual_name}",
                    "parameters": _sanitize_tool_parameters(definition.parameters),
                },
            }
            for definition in definitions
        ]

    def as_mapping(
        self, definitions: list[SessionToolDefinition]
    ) -> dict[str, SessionToolDefinition]:
        return {definition.exposed_name: definition for definition in definitions}

    async def call_tool(
        self,
        definition: SessionToolDefinition,
        arguments: dict[str, Any],
        *,
        ignore_failures: bool = False,
    ) -> dict[str, Any]:
        try:
            return await self._mcp_client.call_tool(
                definition.server_url,
                definition.transport,
                definition.actual_name,
                arguments,
                headers=definition.headers,
            )
        except McpClientError as exc:
            if not ignore_failures:
                raise
            logger.warning(
                "Skipping failed MCP tool call %s at %s",
                definition.exposed_name,
                definition.server_url,
                exc_info=True,
            )
            return {
                "is_error": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"MCP tool call failed: {exc}",
                    }
                ],
            }
