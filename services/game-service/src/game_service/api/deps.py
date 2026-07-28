"""
FastAPI dependency: extract SessionManager from request.app.state.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Path, Request

from game_service.logic.session_manager import SessionManager

SESSION_ID_DESCRIPTION = (
    "Which session to act on. Accepts EITHER the session's UUID `session_id` (e.g. "
    "`3f1a9c2e-5b6d-4a71-9e0f-8c2d4b6a1e73`) OR its human-readable DragnCards room "
    "slug (e.g. `lively-fog-1234`) — both forms work on every endpoint that "
    "identifies a session, including state reads, mutations, and delete. A value "
    "that is neither a well-formed session id nor a known room slug is reported as "
    "not found (HTTP 404). In the rare case that one room slug has more than one "
    "live session attached, the request is rejected (HTTP 409) and the UUID "
    "`session_id` must be used instead. `GET /games` and "
    "`GET /games/by-slug/{room_slug}` both report a session's slug and its "
    "canonical `session_id`."
)

# Shared path-parameter type for routes that identify a session by its UUID or its
# room slug. Keeps the OpenAPI/MCP parameter name (`session_id`) and documentation in
# one place; resolution happens in `SessionManager.resolve_session_id`.
SessionIdentifier = Annotated[str, Path(description=SESSION_ID_DESCRIPTION)]


def get_manager(request: Request) -> SessionManager:
    return request.app.state.session_manager
