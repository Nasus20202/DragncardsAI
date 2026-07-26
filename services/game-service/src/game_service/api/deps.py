"""
FastAPI dependency: extract SessionManager from request.app.state.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Path, Request

from game_service.logic.session_manager import SessionManager

SESSION_ID_DESCRIPTION = (
    "The session's UUID `session_id`. State, mutation, and delete endpoints are "
    "UUID-only: a human-readable room slug is NOT accepted here because the slug is "
    "low-entropy and guessable, so it must never authorize reads/mutations/deletes. "
    "Use `GET /games/by-slug/{room_slug}` to resolve a slug to its canonical "
    "`session_id` first."
)

# Shared path-parameter type for routes that identify a session by its UUID.
# Keeps the OpenAPI/MCP parameter name (`session_id`) and documentation in one place.
SessionIdentifier = Annotated[str, Path(description=SESSION_ID_DESCRIPTION)]


def get_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager
