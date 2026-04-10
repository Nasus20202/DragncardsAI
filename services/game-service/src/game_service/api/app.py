"""
FastAPI application for the Game Service.

Provides a REST HTTP interface to game sessions managed by SessionManager.
Both this API and the MCP server share the same SessionManager instance,
which is stored on app.state.session_manager.

Endpoints:
  GET  /health
  POST /games
  GET  /games
  GET  /games/{id}/state
  POST /games/{id}/actions
  DELETE /games/{id}
  *    /mcp   (MCP streamable-HTTP transport)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from game_service.api.models import (
    ActionRequest,
    CreateGameRequest,
    CreateGameResponse,
    DeleteGameResponse,
    ExecuteActionResponse,
    GameStateResponse,
    HealthResponse,
    ListGamesResponse,
    SessionMetadata,
)
from game_service.mcp.server import create_mcp_server
from game_service.session.manager import (
    SessionError,
    SessionManager,
    SessionNotFoundError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app(session_manager: SessionManager | None = None) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Pass a SessionManager instance to inject it (useful for tests).
    In production, the manager is set on app.state after creation.

    The MCP server is mounted at /mcp using the streamable-HTTP transport,
    sharing the same SessionManager as the REST API.
    """
    # Build MCP session manager upfront so it can be referenced in lifespan
    mcp_http_manager: StreamableHTTPSessionManager | None = None
    if session_manager is not None:
        mcp_server = create_mcp_server(session_manager)
        mcp_http_manager = StreamableHTTPSessionManager(
            app=mcp_server,
            stateless=True,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if mcp_http_manager is not None:
            async with mcp_http_manager.run():
                yield
        else:
            yield

    app = FastAPI(
        title="DragnCards Game Service",
        version="0.1.0",
        description="HTTP REST API and MCP server for programmatic interaction with DragnCards games.",
        lifespan=lifespan,
    )

    # CORS — allow all origins for development; restrict in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Inject session manager if provided
    if session_manager is not None:
        app.state.session_manager = session_manager

    # Mount MCP streamable-HTTP transport at /mcp.
    # Wrap handle_request in a minimal ASGI app class because app.mount()
    # requires an object with __call__, not a bare coroutine function.
    if mcp_http_manager is not None:

        class _MCPApp:
            async def __call__(self, scope, receive, send):
                await mcp_http_manager.handle_request(scope, receive, send)

        app.mount("/mcp", _MCPApp())

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @app.exception_handler(SessionNotFoundError)
    async def not_found_handler(request: Request, exc: SessionNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SessionError)
    async def session_error_handler(request: Request, exc: SessionError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ------------------------------------------------------------------
    # Dependency
    # ------------------------------------------------------------------

    def get_manager(request: Request) -> SessionManager:
        return request.app.state.session_manager

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    async def health():
        """Simple liveness check."""
        return HealthResponse()

    @app.post(
        "/games",
        response_model=CreateGameResponse,
        status_code=201,
        tags=["games"],
        summary="Create a new game session",
    )
    async def create_game(
        body: CreateGameRequest,
        manager: SessionManager = Depends(get_manager),
    ):
        """
        Create a new DragnCards game room for the specified plugin and
        return the session ID plus metadata.
        """
        try:
            session = await manager.create_session(body.plugin_name)
        except SessionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return CreateGameResponse(session=SessionMetadata(**session.to_metadata()))

    @app.get(
        "/games",
        response_model=ListGamesResponse,
        tags=["games"],
        summary="List active game sessions",
    )
    async def list_games(manager: SessionManager = Depends(get_manager)):
        """Return metadata for all active game sessions."""
        sessions = [SessionMetadata(**m) for m in manager.list_sessions()]
        return ListGamesResponse(sessions=sessions)

    @app.get(
        "/games/{session_id}/state",
        response_model=GameStateResponse,
        tags=["games"],
        summary="Get current game state",
    )
    async def get_game_state(
        session_id: str,
        manager: SessionManager = Depends(get_manager),
    ):
        """Return the latest cached game state for the given session."""
        session = await manager.get_session(session_id)
        state = await session.get_state()
        return GameStateResponse(session_id=session_id, state=state)

    @app.post(
        "/games/{session_id}/actions",
        response_model=ExecuteActionResponse,
        tags=["games"],
        summary="Execute a game action",
    )
    async def execute_action(
        session_id: str,
        action: ActionRequest,
        manager: SessionManager = Depends(get_manager),
    ):
        """
        Translate and execute the given action on the specified session.
        Returns the resulting game state.
        """
        session = await manager.get_session(session_id)
        new_state = await session.execute_action(action)
        return ExecuteActionResponse(session_id=session_id, state=new_state)

    @app.delete(
        "/games/{session_id}",
        response_model=DeleteGameResponse,
        tags=["games"],
        summary="Delete a game session",
    )
    async def delete_game(
        session_id: str,
        manager: SessionManager = Depends(get_manager),
    ):
        """Close the WebSocket connection and clean up the session."""
        await manager.delete_session(session_id)
        return DeleteGameResponse(session_id=session_id)

    return app
