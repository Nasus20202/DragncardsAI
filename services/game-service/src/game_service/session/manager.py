"""
Session pool manager.

SessionManager maintains a pool of active GameSession objects and is shared
by both the HTTP API and the MCP server. All public methods are async and safe
to call from concurrent request handlers.

Configuration is injected at construction time:
  - dragncards_http_url: e.g. "http://localhost:4000"
  - dragncards_ws_url:   e.g. "ws://localhost:4000/socket"
  - email / password:    credentials for the bot user account
  - plugin_registry:     dict mapping plugin name -> {id, version, name}
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from game_service.phoenix_client.client import PhoenixClient
from game_service.session.exceptions import SessionError, SessionNotFoundError
from game_service.session.game_session import GameSession
from game_service.session.http_client import create_room, get_auth_token, get_user_id

# Re-export the full exception hierarchy and GameSession so existing callers
# importing from game_service.session.manager continue to work without changes.
from game_service.session.exceptions import (  # noqa: F401
    BadGameStateError,
    SessionError,
    SessionNotFoundError,
    StateUnavailableError,
)
from game_service.session.game_session import GameSession  # noqa: F401

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Maintains a pool of active GameSession objects.

    Both the HTTP API and MCP server share a single SessionManager instance.
    All public methods are async and safe to call from concurrent request handlers.
    """

    def __init__(
        self,
        dragncards_http_url: str,
        dragncards_ws_url: str,
        email: str,
        password: str,
        plugin_registry: dict[str, dict],
    ):
        self._http_url = dragncards_http_url
        self._ws_url = dragncards_ws_url
        self._email = email
        self._password = password
        self._plugin_registry = plugin_registry  # e.g. {"marvel-champions": {...}}
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_session(self, plugin_name: str) -> GameSession:
        """
        Create a new game session:
        1. Authenticate with DragnCards
        2. Create a room via the HTTP API
        3. Connect WebSocket and join the room channel
        4. Wait for initial state broadcast
        Returns the new GameSession.
        """
        plugin_info = self._plugin_registry.get(plugin_name)
        if plugin_info is None:
            available = list(self._plugin_registry.keys())
            raise SessionError(
                f"Plugin {plugin_name!r} not found. Available: {available}"
            )

        # 1. Authenticate
        auth_token = await get_auth_token(self._http_url, self._email, self._password)
        user_id = await get_user_id(self._http_url, auth_token)

        # 2. Create room
        room = await create_room(
            self._http_url,
            auth_token,
            user_id=user_id,
            plugin_id=plugin_info["id"],
            plugin_version=plugin_info["version"],
            plugin_name=plugin_info["name"],
        )
        room_slug = room["slug"]
        logger.info("Created DragnCards room %s for plugin %s", room_slug, plugin_name)

        # 3. Connect WebSocket and join room channel
        ws_client = PhoenixClient(self._ws_url, auth_token=auth_token)
        await ws_client.connect()
        channel = await ws_client.join(f"room:{room_slug}")

        # 4. Wait for initial state (server pushes current_state on join)
        try:
            initial_state = await channel.wait_for_state_update(timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(
                "No initial state received for room %s, will fetch on demand", room_slug
            )
            initial_state = None

        session_id = str(uuid.uuid4())
        session = GameSession(
            session_id=session_id,
            plugin_name=plugin_name,
            plugin_id=plugin_info["id"],
            room_slug=room_slug,
            created_at=datetime.now(timezone.utc),
            client=ws_client,
            channel=channel,
        )
        session._state = initial_state
        session._manager = self

        async with self._lock:
            self._sessions[session_id] = session

        logger.info("Session %s created (room=%s)", session_id, room_slug)
        return session

    async def attach_session(self, plugin_name: str, room_slug: str) -> GameSession:
        """
        Attach to an existing DragnCards room without creating a new one.

        Useful when the service restarts and the bot needs to reconnect to a
        room that is still open on the DragnCards server. The caller is
        responsible for knowing the room_slug (e.g. stored externally).

        Returns a new GameSession connected to the existing room.
        Raises SessionError if the plugin is unknown or the WS join fails.
        """
        plugin_info = self._plugin_registry.get(plugin_name)
        if plugin_info is None:
            available = list(self._plugin_registry.keys())
            raise SessionError(
                f"Plugin {plugin_name!r} not found. Available: {available}"
            )

        # Authenticate
        auth_token = await get_auth_token(self._http_url, self._email, self._password)

        # Connect WebSocket and join existing room channel (no room creation)
        ws_client = PhoenixClient(self._ws_url, auth_token=auth_token)
        await ws_client.connect()
        channel = await ws_client.join(f"room:{room_slug}")

        # Wait for initial state broadcast
        try:
            initial_state = await channel.wait_for_state_update(timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(
                "No initial state received for room %s on attach, will fetch on demand",
                room_slug,
            )
            initial_state = None

        session_id = str(uuid.uuid4())
        session = GameSession(
            session_id=session_id,
            plugin_name=plugin_name,
            plugin_id=plugin_info["id"],
            room_slug=room_slug,
            created_at=datetime.now(timezone.utc),
            client=ws_client,
            channel=channel,
        )
        session._state = initial_state
        session._manager = self

        async with self._lock:
            self._sessions[session_id] = session

        logger.info("Session %s attached to existing room %s", session_id, room_slug)
        return session

    async def get_session(self, session_id: str) -> GameSession:
        """Return a session by ID, raising SessionNotFoundError if absent."""
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        return session

    async def _remove_session(self, session_id: str) -> None:
        """Remove a session from the pool without closing WS (used after close_room)."""
        async with self._lock:
            self._sessions.pop(session_id, None)
        logger.info("Session %s removed from pool (room closed)", session_id)

    async def delete_session(self, session_id: str) -> None:
        """Leave the channel, close the WebSocket, and remove from the pool."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        try:
            await session.client.leave(f"room:{session.room_slug}")
        except Exception as exc:
            logger.warning("Error leaving channel for session %s: %s", session_id, exc)
        try:
            await session.client.disconnect()
        except Exception as exc:
            logger.warning("Error disconnecting session %s: %s", session_id, exc)
        logger.info("Session %s deleted", session_id)

    def list_sessions(self) -> list[dict]:
        """Return metadata for all active sessions."""
        return [s.to_metadata() for s in self._sessions.values()]

    async def close_all(self) -> None:
        """Gracefully close all sessions (called on service shutdown)."""
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            try:
                await self.delete_session(sid)
            except Exception as exc:
                logger.warning("Error closing session %s on shutdown: %s", sid, exc)
