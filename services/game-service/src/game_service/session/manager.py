"""
Game session management.

A GameSession represents a single DragnCards game room with:
- A persistent WebSocket connection (PhoenixClient + Channel)
- Cached latest game state (updated on broadcasts)
- Metadata: session ID, plugin name, creation time, room slug

SessionManager maintains a pool of active sessions, shared by both
the HTTP API and MCP server.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from game_service.phoenix_client.client import (
    Channel,
    PhoenixClient,
    PhoenixChannelError,
    PhxMessage,
)
from game_service.session.actions import GameAction, translate_action

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DragnCards HTTP helpers
# ---------------------------------------------------------------------------


async def _get_auth_token(http_url: str, email: str, password: str) -> str:
    """Authenticate with DragnCards and return a Pow session token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{http_url}/api/v1/session",
            json={"user": {"email": email, "password": password}},
            timeout=10.0,
        )
        resp.raise_for_status()
        return resp.json()["data"]["token"]


async def _create_room(
    http_url: str,
    auth_token: str,
    user_id: int,
    plugin_id: int,
    plugin_version: int,
    plugin_name: str,
) -> dict:
    """Create a DragnCards game room and return the room dict."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{http_url}/api/v1/games",
            headers={"authorization": auth_token},
            json={
                "room": {"user": user_id, "privacy_type": "public"},
                "game_options": {
                    "plugin_id": plugin_id,
                    "plugin_version": plugin_version,
                    "plugin_name": plugin_name,
                    "replay_uuid": None,
                    "external_data": None,
                    "ringsdb_info": None,
                },
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["success"]["room"]


async def _get_user_id(http_url: str, auth_token: str) -> int:
    """Return the numeric user ID for the authenticated user."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{http_url}/api/v1/profile",
            headers={"authorization": auth_token},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # Profile endpoint returns {"user_profile": {...}} not {"data": {...}}
        if "user_profile" in data:
            return data["user_profile"]["id"]
        return data["data"]["id"]


# ---------------------------------------------------------------------------
# Session data class
# ---------------------------------------------------------------------------


@dataclass
class GameSession:
    """Represents a single active game session."""

    session_id: str
    plugin_name: str
    plugin_id: int
    room_slug: str
    created_at: datetime
    client: PhoenixClient
    channel: Channel
    _state: Any = field(default=None, init=False)
    _state_stale: bool = field(default=False, init=False)
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    def __post_init__(self):
        # Subscribe to state broadcasts and cache them
        self.channel.on("current_state", self._on_full_state)
        # state_update carries a delta; we mark state as dirty to re-fetch on next read
        self.channel.on("state_update", self._on_delta)

    def _on_full_state(self, payload: Any) -> None:
        self._state = payload

    def _on_delta(self, payload: Any) -> None:
        # Mark state as stale so the next get_state() fetches fresh data.
        # We don't attempt to apply deltas client-side — DragnCards delta format
        # is complex and not officially documented.
        self._state_stale = True

    async def execute_action(self, action: GameAction, timeout: float = 15.0) -> Any:
        """
        Translate and execute a game action, then return the resulting state.

        Sends a "game_action" message on the channel, waits for the state_update
        delta broadcast, requests the full state via request_state, and returns it.
        Raises SessionError if the action is rejected or times out.
        """
        payload = translate_action(action)
        try:
            # Push action; DragnCards acknowledges immediately then broadcasts state_update
            await self.channel.push("game_action", payload, timeout=timeout)
            # Wait for the state_update delta (signals the action was applied)
            await self.channel.wait_for_event(
                "state_update", "current_state", timeout=timeout
            )
            # Request the full current state
            await self.channel.push("request_state", {}, timeout=timeout)
            # Wait for the resulting current_state broadcast
            new_state = await self.channel.wait_for_state_update(timeout=timeout)
            async with self._state_lock:
                self._state = new_state
                self._state_stale = False
            return new_state
        except PhoenixChannelError as exc:
            raise SessionError(f"Action rejected by DragnCards: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError(
                "Timed out waiting for state update after action"
            ) from exc

    async def get_state(self) -> Any:
        """Return the latest cached game state, re-fetching if stale or absent."""
        async with self._state_lock:
            if self._state is None or self._state_stale:
                try:
                    await self.channel.push("request_state", {}, timeout=10.0)
                    # Wait for the current_state broadcast
                    self._state = await self.channel.wait_for_state_update(timeout=10.0)
                    self._state_stale = False
                except (PhoenixChannelError, asyncio.TimeoutError) as exc:
                    raise SessionError(f"Could not fetch game state: {exc}") from exc
            return self._state

    def to_metadata(self) -> dict:
        """Return session metadata (no full state)."""
        return {
            "session_id": self.session_id,
            "plugin_name": self.plugin_name,
            "plugin_id": self.plugin_id,
            "room_slug": self.room_slug,
            "created_at": self.created_at.isoformat(),
        }


class SessionError(Exception):
    """Raised when a session operation fails."""


class SessionNotFoundError(SessionError):
    """Raised when a session ID is not found."""


# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------


class SessionManager:
    """
    Maintains a pool of active GameSession objects.

    Both the HTTP API and MCP server share a single SessionManager instance.
    All public methods are async and safe to call from concurrent request handlers.

    Configuration is injected at construction time:
      - dragncards_http_url: e.g. "http://localhost:4000"
      - dragncards_ws_url:   e.g. "ws://localhost:4000/socket"
      - email / password:    credentials for the bot user account
      - plugin_registry:     dict mapping plugin name -> {id, version, name}
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
        auth_token = await _get_auth_token(self._http_url, self._email, self._password)
        user_id = await _get_user_id(self._http_url, auth_token)

        # 2. Create room
        room = await _create_room(
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

        async with self._lock:
            self._sessions[session_id] = session

        logger.info("Session %s created (room=%s)", session_id, room_slug)
        return session

    async def get_session(self, session_id: str) -> GameSession:
        """Return a session by ID, raising SessionNotFoundError if absent."""
        session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        return session

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
