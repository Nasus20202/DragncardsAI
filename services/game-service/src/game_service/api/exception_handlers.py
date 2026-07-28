"""
FastAPI exception handlers: map session exception hierarchy to HTTP status codes.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from game_service.logic.session_manager import (
    AmbiguousSessionIdentifierError,
    BadGameStateError,
    SessionError,
    SessionLockedError,
    SessionNotFoundError,
    StateUnavailableError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFoundError)
    async def not_found_handler(request, exc: SessionNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(AmbiguousSessionIdentifierError)
    async def ambiguous_identifier_handler(
        request, exc: AmbiguousSessionIdentifierError
    ):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(BadGameStateError)
    async def bad_game_state_handler(request, exc: BadGameStateError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(StateUnavailableError)
    async def state_unavailable_handler(request, exc: StateUnavailableError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(SessionLockedError)
    async def session_locked_handler(request, exc: SessionLockedError):
        return JSONResponse(status_code=423, content={"detail": str(exc)})

    # SessionError is the base class — must be registered last so the more
    # specific subclass handlers above take priority.
    @app.exception_handler(SessionError)
    async def session_error_handler(request, exc: SessionError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
