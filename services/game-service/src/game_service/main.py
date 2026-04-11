"""
Game Service entrypoint.

Starts both the FastAPI HTTP server (via uvicorn) and the MCP server
(via stdio transport) in the same Python process, sharing one SessionManager.

Usage modes:
  game-service http        — run FastAPI HTTP server on configured port
  game-service mcp         — run MCP server over stdio
  game-service             — defaults to 'http'

Environment variables:
  DRAGNCARDS_HTTP_URL   default: http://localhost:4000
  DRAGNCARDS_WS_URL     default: ws://localhost:4000/socket
  BOT_EMAIL             default: dev@example.com
  BOT_PASSWORD          default: dev_password
  HTTP_HOST             default: 0.0.0.0
  HTTP_PORT             default: 8000
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
BOT_EMAIL = os.environ.get("BOT_EMAIL", "dev@example.com")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "dev_password")
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))

# Plugin registry — maps plugin name to DragnCards plugin metadata.
# Extend this dict to support additional plugins.
PLUGIN_REGISTRY: dict[str, dict] = {
    "marvel-champions": {
        "id": 1,
        "version": 3,
        "name": "Marvel Champions",
    },
}


# ---------------------------------------------------------------------------
# Shared SessionManager factory
# ---------------------------------------------------------------------------


def build_session_manager():
    from game_service.session.manager import SessionManager

    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=BOT_EMAIL,
        password=BOT_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
    )


# ---------------------------------------------------------------------------
# HTTP mode
# ---------------------------------------------------------------------------


def run_http():
    """Start the FastAPI app (+ MCP mounted at /mcp) via uvicorn."""
    import uvicorn
    from fastmcp.utilities.lifespan import combine_lifespans

    from game_service.api.app import create_app
    from game_service.mcp.server import create_mcp_server

    manager = build_session_manager()
    app = create_app(session_manager=manager)
    mcp = create_mcp_server(session_manager=manager, fastapi_app=app)

    # Mount MCP streamable-HTTP transport at /mcp.
    # combine_lifespans ensures both the FastAPI app and the MCP session
    # manager are started and stopped together.
    mcp_asgi = mcp.http_app(path="/")
    app.router.lifespan_context = combine_lifespans(
        app.router.lifespan_context, mcp_asgi.lifespan
    )
    app.mount("/mcp", mcp_asgi)

    logger.info("Starting HTTP server on %s:%s", HTTP_HOST, HTTP_PORT)
    uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)


# ---------------------------------------------------------------------------
# MCP mode (stdio)
# ---------------------------------------------------------------------------


async def run_mcp():
    """Start the MCP server over stdio."""
    from game_service.api.app import create_app
    from game_service.mcp.server import create_mcp_server

    manager = build_session_manager()
    app = create_app(session_manager=manager)
    mcp = create_mcp_server(session_manager=manager, fastapi_app=app)

    logger.info("Starting MCP server (stdio transport)")
    mcp.run(transport="stdio")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "http"

    if mode == "http":
        run_http()
    elif mode == "mcp":
        asyncio.run(run_mcp())
    else:
        print(f"Unknown mode {mode!r}. Use 'http' or 'mcp'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
