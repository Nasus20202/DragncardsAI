"""MCP server for the Game Service."""

from __future__ import annotations

import logging

from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap

logger = logging.getLogger(__name__)


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
        route_maps=[
            # /health is noise for an LLM client
            RouteMap(pattern=r"^/health$", mcp_type=MCPType.EXCLUDE),
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
            RouteMap(pattern=r"^/games/[^/]+/load-prebuilt-deck$", mcp_type=MCPType.TOOL),
        ],
    )
