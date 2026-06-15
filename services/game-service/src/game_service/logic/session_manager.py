"""
Session pool manager.

SessionManager maintains a pool of active GameSession objects and is shared
by both the HTTP API and the MCP server. All public methods are async and safe
to call from concurrent request handlers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from game_service.dragncards.http_client import create_room, get_auth_token, get_user_id
from game_service.catalog.service import load_prebuilt_deck
from game_service.logic.exceptions import (
    BadGameStateError,
    SessionError,
    SessionLockedError,
    SessionNotFoundError,
    SnapshotValidationError,
    StateUnavailableError,
)
from game_service.logic.session import GameSession
from game_service.coordination.session_store import InMemorySessionStore, SessionStore
from game_service.phoenix_client.client import PhoenixClient
from game_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class SessionManager:
    """Maintains a pool of active GameSession objects."""

    def __init__(
        self,
        dragncards_http_url: str,
        dragncards_ws_url: str,
        email: str,
        password: str,
        plugin_registry: dict[str, dict],
        session_store: SessionStore | None = None,
    ):
        self._http_url = dragncards_http_url
        self._ws_url = dragncards_ws_url
        self._email = email
        self._password = password
        self._plugin_registry = plugin_registry
        self._session_store = session_store or InMemorySessionStore()
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()

    async def restore_sessions(self) -> None:
        with tracer.start_as_current_span("game_service.restore_sessions"):
            records = await self._session_store.list_sessions()
            for record in records:
                session_id = record["session_id"]
                if session_id in self._sessions:
                    continue
                await self._restore_session(record)

    def _get_plugin_info(self, plugin_name: str) -> dict[str, Any]:
        plugin_info = self._plugin_registry.get(plugin_name)
        if plugin_info is None:
            available = list(self._plugin_registry.keys())
            raise SessionError(
                f"Plugin {plugin_name!r} not found. Available: {available}"
            )
        return plugin_info

    async def _connect_room_channel(
        self, room_slug: str, auth_token: str
    ) -> tuple[PhoenixClient, Any, Any]:
        ws_client = PhoenixClient(self._ws_url, auth_token=auth_token)
        await ws_client.connect()
        channel = await ws_client.join(f"room:{room_slug}")
        initial_state = await self._wait_for_initial_state(channel, room_slug)
        return ws_client, channel, initial_state

    async def _wait_for_initial_state(self, channel: Any, room_slug: str) -> Any:
        try:
            return await channel.wait_for_state_update(timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(
                "No initial state received for room %s, will fetch on demand",
                room_slug,
            )
            return None

    def _build_session(
        self,
        *,
        session_id: str,
        plugin_name: str,
        plugin_id: int,
        room_slug: str,
        created_at: datetime,
        client: PhoenixClient,
        channel: Any,
        initial_state: Any,
    ) -> GameSession:
        session = GameSession(
            session_id=session_id,
            plugin_name=plugin_name,
            plugin_id=plugin_id,
            room_slug=room_slug,
            created_at=created_at,
            client=client,
            channel=channel,
            initial_state=initial_state,
            on_close=lambda: self._remove_session(session_id),
        )
        return session

    async def _register_session(
        self, session: GameSession, *, persist: bool = True
    ) -> GameSession:
        if persist:
            await self._session_store.put_session(session.to_metadata())

        async with self._lock:
            self._sessions[session.session_id] = session

        return session

    async def _restore_session(self, record: dict[str, Any]) -> GameSession:
        with tracer.start_as_current_span(
            "game_service.restore_session",
            attributes={"game.plugin.name": record["plugin_name"]},
        ):
            plugin_name = record["plugin_name"]
            plugin_info = self._plugin_registry.get(plugin_name)
            if plugin_info is None:
                raise SessionError(
                    f"Cannot restore session {record['session_id']!r}: plugin {plugin_name!r} is not available"
                )

            auth_token = await get_auth_token(
                self._http_url, self._email, self._password
            )
            ws_client, channel, initial_state = await self._connect_room_channel(
                record["room_slug"], auth_token
            )
            session = self._build_session(
                session_id=record["session_id"],
                plugin_name=plugin_name,
                plugin_id=plugin_info["id"],
                room_slug=record["room_slug"],
                created_at=datetime.fromisoformat(record["created_at"]),
                client=ws_client,
                channel=channel,
                initial_state=initial_state,
            )
            await self._register_session(session, persist=False)

            logger.info(
                "Restored session %s from coordination store", session.session_id
            )
            return session

    async def _auto_seat(self, session: GameSession, user_id: int) -> None:
        try:
            state = await session.get_state()
        except SessionError as exc:
            logger.warning(
                "auto_seat: session_id=%s state unavailable: %s",
                session.session_id,
                exc,
            )
            return

        if not isinstance(state, dict):
            logger.warning(
                "auto_seat: session_id=%s invalid state payload", session.session_id
            )
            return

        game = state.get("game")
        if not isinstance(game, dict):
            logger.warning(
                "auto_seat: session_id=%s missing game payload", session.session_id
            )
            return

        def _seat_key(item: tuple[str, object]) -> tuple[int, str]:
            player_n = item[0]
            suffix = player_n[6:] if player_n.startswith("player") else player_n
            try:
                return (int(suffix), player_n)
            except ValueError:
                return (10_000, player_n)

        player_info = game.get("playerInfo")
        if isinstance(player_info, dict):
            for info in player_info.values():
                if isinstance(info, dict) and info.get("id") == user_id:
                    logger.info(
                        "auto_seat: session_id=%s user already seated",
                        session.session_id,
                    )
                    return

            ordered_seats = sorted(player_info.items(), key=_seat_key)
            for player_n, info in ordered_seats:
                if info is None or not isinstance(info, dict) or info.get("id") is None:
                    try:
                        await session.set_seat(player_index=player_n, user_id=user_id)
                        logger.info(
                            "auto_seat: session_id=%s assigned user=%s to %s",
                            session.session_id,
                            user_id,
                            player_n,
                        )
                        return
                    except Exception as exc:
                        logger.warning(
                            "auto_seat: session_id=%s seat %s failed: %s",
                            session.session_id,
                            player_n,
                            exc,
                        )

            logger.info("auto_seat: session_id=%s no vacant seats", session.session_id)
            return

        player_data = game.get("playerData")
        if not isinstance(player_data, dict):
            logger.warning(
                "auto_seat: session_id=%s missing playerInfo and playerData",
                session.session_id,
            )
            return

        for info in player_data.values():
            if isinstance(info, dict) and info.get("user_id") == user_id:
                logger.info(
                    "auto_seat: session_id=%s user already seated",
                    session.session_id,
                )
                return

        ordered_seats = sorted(player_data.items(), key=_seat_key)
        for player_n, info in ordered_seats:
            if not isinstance(info, dict) or info.get("user_id") is None:
                try:
                    await session.set_seat(player_index=player_n, user_id=user_id)
                    logger.info(
                        "auto_seat: session_id=%s assigned user=%s to %s",
                        session.session_id,
                        user_id,
                        player_n,
                    )
                    return
                except Exception as exc:
                    logger.warning(
                        "auto_seat: session_id=%s seat %s failed: %s",
                        session.session_id,
                        player_n,
                        exc,
                    )

        logger.info("auto_seat: session_id=%s no vacant seats", session.session_id)

    async def create_session(self, plugin_name: str) -> GameSession:
        with tracer.start_as_current_span(
            "game_service.create_session",
            attributes={"game.plugin.name": plugin_name},
        ):
            plugin_info = self._get_plugin_info(plugin_name)

            auth_token = await get_auth_token(
                self._http_url, self._email, self._password
            )
            user_id = await get_user_id(self._http_url, auth_token)

            room = await create_room(
                self._http_url,
                auth_token,
                user_id=user_id,
                plugin_id=plugin_info["id"],
                plugin_version=plugin_info["version"],
                plugin_name=plugin_info["name"],
            )
            room_slug = room["slug"]
            logger.info(
                "Created DragnCards room %s for plugin %s", room_slug, plugin_name
            )

            ws_client, channel, initial_state = await self._connect_room_channel(
                room_slug, auth_token
            )

            session_id = str(uuid.uuid4())
            session = self._build_session(
                session_id=session_id,
                plugin_name=plugin_name,
                plugin_id=plugin_info["id"],
                room_slug=room_slug,
                created_at=datetime.now(timezone.utc),
                client=ws_client,
                channel=channel,
                initial_state=initial_state,
            )
            await self._register_session(session)
            await self._auto_seat(session, user_id)

            logger.info("Session %s created (room=%s)", session_id, room_slug)
            return session

    async def attach_session(self, plugin_name: str, room_slug: str) -> GameSession:
        plugin_info = self._get_plugin_info(plugin_name)

        auth_token = await get_auth_token(self._http_url, self._email, self._password)
        user_id = await get_user_id(self._http_url, auth_token)
        ws_client, channel, initial_state = await self._connect_room_channel(
            room_slug, auth_token
        )

        session_id = str(uuid.uuid4())
        session = self._build_session(
            session_id=session_id,
            plugin_name=plugin_name,
            plugin_id=plugin_info["id"],
            room_slug=room_slug,
            created_at=datetime.now(timezone.utc),
            client=ws_client,
            channel=channel,
            initial_state=initial_state,
        )
        await self._register_session(session)
        await self._auto_seat(session, user_id)

        logger.info("Session %s attached to existing room %s", session_id, room_slug)
        return session

    async def get_session(self, session_id: str) -> GameSession:
        session = self._sessions.get(session_id)
        if session is None:
            record = await self._session_store.get_session(session_id)
            if record is None:
                raise SessionNotFoundError(f"Session {session_id!r} not found")
            session = await self._restore_session(record)
        return session

    @asynccontextmanager
    async def session_operation_lock(
        self,
        session_id: str,
        *,
        wait_timeout: float = 5.0,
        lease_ttl: float = 30.0,
    ):
        owner_token = str(uuid.uuid4())
        acquired = await self._session_store.acquire_session_lock(
            session_id=session_id,
            owner_token=owner_token,
            lease_ttl=lease_ttl,
            wait_timeout=wait_timeout,
        )
        if not acquired:
            raise SessionLockedError(
                f"Session {session_id!r} is busy; could not acquire operation lock within {wait_timeout:.1f}s"
            )
        try:
            yield
        finally:
            try:
                await self._session_store.release_session_lock(session_id, owner_token)
            except Exception as exc:
                logger.warning(
                    "Failed to release operation lock for session %s: %s",
                    session_id,
                    exc,
                )

    async def _remove_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
        await self._session_store.delete_session(session_id)
        logger.info("Session %s removed from pool (room closed)", session_id)

    async def delete_session(self, session_id: str) -> None:
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
        await self._session_store.delete_session(session_id)
        logger.info("Session %s deleted", session_id)

    async def load_prebuilt_deck(self, session_id: str, deck_id: str) -> Any:
        async with self.session_operation_lock(session_id):
            session = await self.get_session(session_id)
            deck = load_prebuilt_deck(deck_id, session.plugin_name)
            if deck is None:
                raise SessionError(
                    f"Prebuilt deck {deck_id!r} not found for plugin {session.plugin_name!r}"
                )
            before_state = await session.get_state()
            result = await session.load_prebuilt_deck(deck.get("deck_id", deck_id))

            await asyncio.sleep(0.5)
            for _ in range(10):
                after_state = await session.get_state()
                if isinstance(after_state, dict):
                    game = after_state.get("game")
                    if isinstance(game, dict) and isinstance(
                        game.get("messages"), list
                    ):
                        messages = game["messages"]
                        for message in reversed(messages):
                            if not isinstance(message, str):
                                continue
                            if (
                                "ABORT:" in message
                                or "Error in Marvel Champions triggered" in message
                            ):
                                raise SessionError(message)
                        if game.get("loadedCardIds") or game.get("loadCardsHistory"):
                            return result
                await asyncio.sleep(0.2)

            return result

    async def list_sessions(self) -> list[dict]:
        records = await self._session_store.list_sessions()
        return [dict(record) for record in records]

    async def close_all(self) -> None:
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            try:
                await self.delete_session(sid)
            except Exception as exc:
                logger.warning("Error closing session %s on shutdown: %s", sid, exc)
