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
  HTTP_PORT             default: 4001
"""

from __future__ import annotations

import logging
import os
import sys
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

from game_service.telemetry import setup_telemetry

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
BOT_EMAIL = os.environ.get("BOT_EMAIL", "dev@example.com")
BOT_PASSWORD = os.environ.get("BOT_PASSWORD", "dev_password")
VALKEY_URL = os.environ.get("VALKEY_URL", "redis://localhost:6380/0")
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "4001"))

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
    from game_service.coordination.session_store import (
        InMemorySessionStore,
        ValkeySessionStore,
    )
    from game_service.logic.session_manager import SessionManager

    parsed = urlparse(VALKEY_URL)
    use_in_memory = os.environ.get(
        "GAME_SERVICE_USE_IN_MEMORY_SESSION_STORE", ""
    ).lower() in {
        "1",
        "true",
        "yes",
    }

    if use_in_memory:
        session_store = InMemorySessionStore()
        logger.warning("Using in-memory session coordination store")
    else:
        session_store = ValkeySessionStore(VALKEY_URL)
        logger.info(
            "Using Valkey session coordination store at %s:%s",
            parsed.hostname,
            parsed.port or 6379,
        )

    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=BOT_EMAIL,
        password=BOT_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
        session_store=session_store,
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

    setup_telemetry()
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

    @app.on_event("startup")
    async def _restore_sessions() -> None:
        try:
            await manager.restore_sessions()
        except OSError as exc:
            if os.environ.get(
                "GAME_SERVICE_USE_IN_MEMORY_SESSION_STORE", ""
            ).lower() in {
                "1",
                "true",
                "yes",
            }:
                logger.warning(
                    "Skipping session restore because local session store is unavailable: %s",
                    exc,
                )
            else:
                raise

    logger.info("Starting HTTP server on %s:%s", HTTP_HOST, HTTP_PORT)
    uvicorn.run(app, host=HTTP_HOST, port=HTTP_PORT)


# ---------------------------------------------------------------------------
# MCP mode (stdio)
# ---------------------------------------------------------------------------


def run_mcp():
    """Start the MCP server over stdio."""
    from game_service.api.app import create_app
    from game_service.mcp.server import create_mcp_server

    setup_telemetry()
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
        run_mcp()
    else:
        print(f"Unknown mode {mode!r}. Use 'http' or 'mcp'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
