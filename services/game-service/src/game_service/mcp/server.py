"""MCP server for the Game Service."""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, OpenAPITool, RouteMap

logger = logging.getLogger(__name__)


def _refuse_unknown_tool_arguments(route: Any, component: Any) -> None:
    """Re-apply ``additionalProperties: false`` at a tool's flattened schema root.

    FastMCP builds a tool's parameters by flattening the request body's
    properties alongside the path parameters into a fresh object and never copies
    the body model's ``additionalProperties`` flag up to that root, so an
    argument the route's parameter map does not know is dropped by the request
    director with a log warning and the model sees a successful call. The flag at
    the root is what a strict client validates a generated call against, so a
    hallucinated argument is refused at inference time instead.

    This service predates ``dragncards_common.mcp`` and keeps an equivalent copy
    of the shared bootstrap; this hook mirrors the one that lives there, and the
    two must stay in step.
    """
    if not isinstance(component, OpenAPITool):
        return
    parameters = getattr(component, "parameters", None)
    if isinstance(parameters, dict):
        parameters["additionalProperties"] = False


def create_mcp_server(session_manager, fastapi_app) -> FastMCP:
    """
    Build and return a FastMCP server wired to the given SessionManager.

    Tools and resources are derived automatically from the FastAPI app's OpenAPI
    schema. Read-only GET routes are mapped to MCP resources/templates where that
    produces a better read surface than a tool call.
    """
    logger.info("Initializing MCP server from FastAPI OpenAPI schema")
    return FastMCP.from_fastapi(
        app=fastapi_app,
        name="game-service",
        mcp_component_fn=_refuse_unknown_tool_arguments,
        route_maps=[
            # /health is noise for an LLM client
            RouteMap(pattern=r"^/health$", mcp_type=MCPType.EXCLUDE),
            # /capabilities tells a client what the server supports — the
            # server's own state, like the probes — and is not a tool an agent
            # needs to call. A client asks over HTTP before it sends anything.
            RouteMap(pattern=r"^/capabilities$", mcp_type=MCPType.EXCLUDE),
            # snapshot import/export are privileged HTTP-only operations
            RouteMap(pattern=r"^/games/[^/]+/snapshot$", mcp_type=MCPType.EXCLUDE),
            # room control and room observability endpoints are HTTP-only
            RouteMap(pattern=r"^/games/[^/]+/reset$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/seat$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/spectator$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/alert$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/replay$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/player-count$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/alerts$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/gui-update$", mcp_type=MCPType.EXCLUDE),
            # debug endpoints are HTTP-only (raw state, generic actions, raw DragnLang)
            RouteMap(pattern=r"^/games/[^/]+/state/raw$", mcp_type=MCPType.EXCLUDE),
            RouteMap(
                pattern=r"^/games/[^/]+/actions$",
                methods=["POST"],
                mcp_type=MCPType.EXCLUDE,
            ),
            RouteMap(pattern=r"^/games/[^/]+/actions/raw$", mcp_type=MCPType.EXCLUDE),
            RouteMap(
                pattern=r"^/games/[^/]+/load-prebuilt-deck$", mcp_type=MCPType.TOOL
            ),
        ],
    )
