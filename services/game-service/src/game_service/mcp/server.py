"""
MCP server for the Game Service.

Auto-generated from the FastAPI app via FastMCP.from_fastapi(), so tool
schemas, descriptions, and parameter validation are always in sync with
the HTTP API — no manual tool definitions required.

The three game:// resources (state, alerts, gui-update) are registered
manually because they expose in-process push-buffered data that has no
OpenAPI equivalent.
"""

from __future__ import annotations

import json
import logging

from fastmcp import FastMCP
from fastmcp.server.providers.openapi import MCPType, RouteMap

from game_service.session.manager import SessionManager

logger = logging.getLogger(__name__)


def create_mcp_server(session_manager: SessionManager, fastapi_app) -> FastMCP:
    """
    Build and return a FastMCP server wired to the given SessionManager.

    Tools are derived automatically from the FastAPI app's OpenAPI schema.
    The /health route is excluded — it is noise for an LLM client.

    Resources are registered manually because they expose in-process state
    (alert buffer, GUI update cache) that cannot be expressed in OpenAPI.
    """
    mcp = FastMCP.from_fastapi(
        app=fastapi_app,
        name="game-service",
        route_maps=[
            # /health is noise for an LLM client
            RouteMap(pattern=r"^/health$", mcp_type=MCPType.EXCLUDE),
            # alerts and gui-update are exposed as resources (game:// URIs) below;
            # exclude them from tools to avoid duplication
            RouteMap(pattern=r"^/games/[^/]+/alerts$", mcp_type=MCPType.EXCLUDE),
            RouteMap(pattern=r"^/games/[^/]+/gui-update$", mcp_type=MCPType.EXCLUDE),
        ],
    )

    # ------------------------------------------------------------------
    # Resources — read directly from the in-process SessionManager,
    # no HTTP round-trip required.
    # ------------------------------------------------------------------

    @mcp.resource("game://{session_id}/state")
    async def game_state(session_id: str) -> str:
        """Current game state as JSON for the given session."""
        session = await session_manager.get_session(session_id)
        state = await session.get_state()
        return json.dumps(state, indent=2) if state is not None else "null"

    @mcp.resource("game://{session_id}/alerts")
    async def game_alerts(session_id: str) -> str:
        """Buffered room alerts as JSON (up to 50, oldest first)."""
        session = await session_manager.get_session(session_id)
        return json.dumps(session.get_alerts(), indent=2)

    @mcp.resource("game://{session_id}/gui-update")
    async def game_gui_update(session_id: str) -> str:
        """Latest GUI update hints per player as JSON."""
        session = await session_manager.get_session(session_id)
        return json.dumps(session.get_gui_updates(), indent=2)

    return mcp
