"""
FastAPI dependency: extract SessionManager from request.app.state.
"""

from __future__ import annotations

from fastapi import Request

from game_service.session.manager import SessionManager


def get_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager
