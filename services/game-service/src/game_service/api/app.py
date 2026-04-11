"""
FastAPI application factory for the Game Service.

Wires together routers, exception handlers, and middleware.
The MCP server is mounted externally by main.py so this module
has no dependency on FastMCP.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from game_service.api.exception_handlers import register_exception_handlers
from game_service.api.routers import games, meta, room_control, room_events
from game_service.api.routers import cards as cards_router
from game_service.session.manager import SessionManager

logger = logging.getLogger(__name__)


def create_app(session_manager: SessionManager | None = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Pass a SessionManager to inject it at construction time (useful for tests).
    In production the manager is always provided here; main.py builds it first.
    """
    app = FastAPI(
        title="DragnCards Game Service",
        version="0.1.0",
        description="HTTP REST API and MCP server for programmatic interaction with DragnCards games.",
    )

    # CORS — allow all origins for development; restrict in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if session_manager is not None:
        app.state.session_manager = session_manager

    register_exception_handlers(app)

    app.include_router(meta.router)
    app.include_router(games.router)
    app.include_router(room_control.router)
    app.include_router(room_events.router)
    app.include_router(cards_router.router)

    return app
