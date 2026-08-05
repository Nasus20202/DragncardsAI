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
  DRAGNCARDS_AUTH_CACHE_TTL_SECONDS  default: 900 (0 disables the cache)
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

from game_service.dragncards.auth_cache import (
    DEFAULT_TTL_SECONDS as DEFAULT_AUTH_CACHE_TTL_SECONDS,
)
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
# History ingestion is on by default; set HISTORY_INGEST_ENABLED=false to disable.
HISTORY_INGEST_ENABLED = os.environ.get(
    "HISTORY_INGEST_ENABLED", "true"
).lower() not in {
    "0",
    "false",
    "no",
}
# The history-service ingests from a single shared Valkey reached by all three
# producers/consumers (the agent-orchestrator Valkey). This is intentionally
# separate from the game-service's own session-store Valkey (VALKEY_URL).
# Defaults to the shared orchestrator Valkey for local runs.
HISTORY_VALKEY_URL = os.environ.get("HISTORY_VALKEY_URL", "redis://localhost:6381/0")


def _positive_float_env(name: str, default: float) -> float:
    """Parse a strictly-positive float env var, falling back to ``default``.

    Used for the ephemeral reconstruction reaper knobs. A missing, malformed, or
    non-positive value is rejected (logged) and the default is used so a typo can
    never disable reaping or set a degenerate interval.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value <= 0:
        logger.warning(
            "%s must be positive (got %s); using default %s", name, value, default
        )
        return default
    return value


def _non_negative_float_env(name: str, default: float) -> float:
    """Parse a float env var where ``0`` is a meaningful value, not a typo.

    Separate from :func:`_positive_float_env` because the credential cache TTL
    uses ``0`` to mean "do not cache". Folding the two would either turn that
    switch into a silently ignored typo or let a negative interval through to the
    reaper.
    """
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using default %s", name, raw, default)
        return default
    if value < 0:
        logger.warning(
            "%s must not be negative (got %s); using default %s", name, value, default
        )
        return default
    return value


# How long an ephemeral reconstruction session may live before the server-side
# reaper reclaims it (session + DragnCards room), even if the client never tore
# it down. Default 30 minutes.
EPHEMERAL_SESSION_TTL_SECONDS = _positive_float_env(
    "EPHEMERAL_SESSION_TTL_SECONDS", 1800.0
)
# How often the reaper checks for expired ephemeral sessions. Default 60s.
EPHEMERAL_REAPER_INTERVAL_SECONDS = _positive_float_env(
    "EPHEMERAL_REAPER_INTERVAL_SECONDS", 60.0
)

# How long the DragnCards session token and user id are reused out of Valkey
# before being re-derived. DragnCards keeps an issued token valid for 30 minutes,
# so the default is half that lifetime. Set to 0 to authenticate once per room, as
# this service did before the cache existed.
DRAGNCARDS_AUTH_CACHE_TTL_SECONDS = _non_negative_float_env(
    "DRAGNCARDS_AUTH_CACHE_TTL_SECONDS", DEFAULT_AUTH_CACHE_TTL_SECONDS
)

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
    from game_service.coordination.history_emitter import build_history_emitter
    from game_service.coordination.session_store import (
        InMemorySessionStore,
        ValkeySessionStore,
        _RespConnection,
    )
    from game_service.dragncards.auth_cache import DragnCardsAuthCache
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

    history_emitter = build_history_emitter(
        enabled=HISTORY_INGEST_ENABLED,
        valkey_url=None if use_in_memory else HISTORY_VALKEY_URL,
    )
    if HISTORY_INGEST_ENABLED and not use_in_memory:
        history_valkey = urlparse(HISTORY_VALKEY_URL)
        logger.info(
            "History ingestion enabled; emitting to Valkey stream history:ingest "
            "at %s:%s",
            history_valkey.hostname,
            history_valkey.port or 6379,
        )
    else:
        logger.info("History ingestion disabled")

    # The credential cache shares the session-store Valkey: both hold ephemeral
    # coordination data for this service, and the connection is stateless (one TCP
    # connection per command), so there is nothing to pool or hand around. With the
    # in-memory session store selected there is no Valkey to use, and the cache is
    # left inert — the same as setting the TTL to 0.
    auth_cache = DragnCardsAuthCache(
        DRAGNCARDS_HTTP_URL,
        BOT_EMAIL,
        BOT_PASSWORD,
        valkey=(
            None
            if use_in_memory
            else _RespConnection(parsed.hostname or "localhost", parsed.port or 6379)
        ),
        ttl_seconds=DRAGNCARDS_AUTH_CACHE_TTL_SECONDS,
    )
    if auth_cache.enabled:
        logger.info(
            "DragnCards credential cache enabled (ttl=%.0fs key=%s)",
            DRAGNCARDS_AUTH_CACHE_TTL_SECONDS,
            auth_cache.key,
        )
    else:
        logger.info(
            "DragnCards credential cache disabled; authenticating once per room"
        )

    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=BOT_EMAIL,
        password=BOT_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
        session_store=session_store,
        history_emitter=history_emitter,
        ephemeral_session_ttl_seconds=EPHEMERAL_SESSION_TTL_SECONDS,
        ephemeral_reaper_interval_seconds=EPHEMERAL_REAPER_INTERVAL_SECONDS,
        auth_cache=auth_cache,
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

    @app.on_event("startup")
    async def _start_ephemeral_reaper() -> None:
        # Background safety net: reclaims ephemeral reconstruction sessions whose
        # client never issued a teardown (lost connection / crash / power-off).
        manager.start_ephemeral_reaper()

    @app.on_event("shutdown")
    async def _stop_ephemeral_reaper() -> None:
        await manager.stop_ephemeral_reaper()

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
