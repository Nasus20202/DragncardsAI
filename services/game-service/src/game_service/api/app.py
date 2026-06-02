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
from game_service.api.routers import cards as cards_router
from game_service.api.routers import load_prebuilt_deck as load_prebuilt_deck_router
from game_service.api.routers import prebuilt_sets as prebuilt_sets_router
from game_service.api.routers import (
    game_actions,
    game_lifecycle,
    game_room,
    game_state,
    meta,
)
from game_service.logic.session_manager import SessionManager
from game_service.telemetry import instrument_fastapi_app

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
    instrument_fastapi_app(app)

    app.include_router(meta.router)
    app.include_router(game_lifecycle.router)
    app.include_router(game_state.router)
    app.include_router(game_actions.router)
    # Explicit per-action helper endpoints (typed helpers)
    from game_service.api.routers import game_action_helpers
    app.include_router(game_action_helpers.router)
    app.include_router(game_room.router)
    app.include_router(cards_router.router)
    app.include_router(load_prebuilt_deck_router.router)
    app.include_router(prebuilt_sets_router.router)

    return app
