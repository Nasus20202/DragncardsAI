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
from game_service.coordination.history_emitter import (
    HistoryEmitter,
    NullHistoryEmitter,
)
from game_service.logic.exceptions import (
    AmbiguousSessionIdentifierError,
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
        history_emitter: HistoryEmitter | None = None,
        ephemeral_session_ttl_seconds: float = 1800.0,
        ephemeral_reaper_interval_seconds: float = 60.0,
    ):
        self._http_url = dragncards_http_url
        self._ws_url = dragncards_ws_url
        self._email = email
        self._password = password
        self._plugin_registry = plugin_registry
        self._session_store = session_store or InMemorySessionStore()
        self._history_emitter = history_emitter or NullHistoryEmitter()
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()
        self._ephemeral_session_ttl_seconds = ephemeral_session_ttl_seconds
        self._ephemeral_reaper_interval_seconds = ephemeral_reaper_interval_seconds
        self._reaper_task: asyncio.Task[None] | None = None

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
        ephemeral: bool = False,
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
            history_emitter=self._history_emitter,
            ephemeral=ephemeral,
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
                ephemeral=bool(record.get("ephemeral", False)),
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

    async def create_session(
        self, plugin_name: str, *, ephemeral: bool = False
    ) -> GameSession:
        with tracer.start_as_current_span(
            "game_service.create_session",
            attributes={
                "game.plugin.name": plugin_name,
                "game.session.ephemeral": ephemeral,
            },
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
                ephemeral=ephemeral,
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

    @staticmethod
    def _as_canonical_uuid(value: str) -> str | None:
        """Return ``value`` as a canonical UUID string, or ``None`` if it is not one.

        A valid but non-canonical UUID (e.g. uppercase or braced) is normalized so
        that it still matches the canonical id stored on the session.
        """
        try:
            return str(uuid.UUID(str(value)))
        except ValueError, AttributeError, TypeError:
            return None

    async def resolve_session_id(self, identifier: str) -> str:
        """Resolve a session UUID *or* a human-readable room slug to a session id.

        Every session-identifying path (state reads, mutations, and deletes) funnels
        through here, so an operator or an agent can work in terms of the readable
        DragnCards room slug (`lively-fog-1234`) instead of the opaque UUID. A
        well-formed UUID is returned in canonical form without a store round-trip, so
        an already-removed session still resolves and delete stays idempotent;
        anything else is treated as a room slug and resolved through the session pool
        or the session store's slug index.

        Raises ``SessionNotFoundError`` when the value is neither a UUID nor a known
        room slug, and ``AmbiguousSessionIdentifierError`` when the slug matches more
        than one live session.
        """
        canonical = self._as_canonical_uuid(identifier)
        if canonical is not None:
            return canonical
        return await self._resolve_room_slug(identifier)

    async def _resolve_room_slug(self, room_slug: str) -> str:
        """Resolve a room slug to a session id via the pool, then the store index."""
        # In-pool scan first: it is also the only place duplicate slugs are
        # detectable, because `attach_session` may create more than one session for
        # the same DragnCards room and the store's slug index is last-writer-wins.
        live_matches = sorted(
            {
                session.session_id
                for session in self._sessions.values()
                if session.room_slug == room_slug
            }
        )
        if len(live_matches) > 1:
            raise AmbiguousSessionIdentifierError(
                f"Room slug {room_slug!r} matches {len(live_matches)} sessions "
                f"({', '.join(live_matches)}); use the session's `session_id` instead."
            )
        if live_matches:
            return live_matches[0]

        session_id = await self._session_store.get_session_id_by_slug(room_slug)
        if session_id is not None:
            if await self._session_store.get_session(session_id) is not None:
                return session_id
        raise SessionNotFoundError(
            f"{room_slug!r} is neither a session id nor a known room slug"
        )

    async def lookup_session_by_slug(self, room_slug: str) -> dict[str, Any]:
        """Resolve a human-readable ``room_slug`` to its session metadata.

        A convenience read: every session endpoint already accepts a room slug in
        the ``session_id`` position, so this is only needed when the caller wants the
        full session metadata (including the canonical UUID ``session_id``) rather
        than acting on the session. Raises ``SessionNotFoundError`` when the slug is
        unknown.
        """
        session_id = await self._resolve_room_slug(room_slug)
        session = self._sessions.get(session_id)
        if session is not None:
            return session.to_metadata()
        record = await self._session_store.get_session(session_id)
        if record is None:
            raise SessionNotFoundError(f"Session for room slug {room_slug!r} not found")
        return dict(record)

    async def get_session(self, session_id: str) -> GameSession:
        session_id = await self.resolve_session_id(session_id)
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
        # Resolve first so a slug-addressed and a UUID-addressed operation on the
        # same session contend for the same lock key.
        session_id = await self.resolve_session_id(session_id)
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
        session_id = await self.resolve_session_id(session_id)
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        if session.ephemeral:
            # An ephemeral reconstruction owns its DragnCards room outright (it
            # was created solely to view a past moment), so tearing the session
            # down must close the room too — otherwise every "board at this
            # event" view leaves a room behind forever. The room event has to be
            # pushed while the channel is still joined, hence before the leave
            # below. Best-effort: a failure here must not block the teardown.
            try:
                await session.close_room()
            except Exception as exc:
                logger.warning(
                    "Error closing room %s for ephemeral session %s: %s",
                    session.room_slug,
                    session_id,
                    exc,
                )
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

    # ------------------------------------------------------------------
    # Ephemeral reconstruction reaper
    # ------------------------------------------------------------------
    #
    # Ephemeral reconstruction sessions are view-only branches created for the
    # dashboard "open board at this event" feature. Client teardown
    # (DELETE /games/{id}) is the fast path, but it is best-effort only: a lost
    # network connection, tab crash, or power loss can leave the session and its
    # DragnCards room orphaned. This background reaper deletes ephemeral sessions
    # (and their rooms) once they are older than the configured TTL, so a crashed
    # client can never leak one. Non-ephemeral sessions are never touched. The
    # ephemeral tag and created_at live in the session store (no in-memory-only
    # durable state), so reaping is correct across service instances and restarts.

    async def reap_expired_ephemeral_sessions(self) -> int:
        """Delete ephemeral sessions older than the configured TTL.

        Returns the number of sessions reaped. Reads candidates from the session
        store (the durable source of the ``ephemeral`` tag + ``created_at``), so
        a session that was never loaded into this process's pool is still
        reclaimed. Idempotent: a record already removed (e.g. by an explicit
        client teardown) is simply skipped.
        """
        now = datetime.now(timezone.utc)
        ttl = self._ephemeral_session_ttl_seconds
        try:
            records = await self._session_store.list_sessions()
        except Exception as exc:  # best-effort: never crash the reaper loop
            logger.warning("ephemeral reaper: failed to list sessions: %s", exc)
            return 0

        reaped = 0
        for record in records:
            if not record.get("ephemeral"):
                continue
            created_raw = record.get("created_at")
            if not isinstance(created_raw, str):
                continue
            try:
                created_at = datetime.fromisoformat(created_raw)
            except ValueError:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age = (now - created_at).total_seconds()
            if age < ttl:
                continue
            session_id = record["session_id"]
            if await self._reap_ephemeral_session(session_id):
                reaped += 1
        if reaped:
            logger.info("ephemeral reaper: reclaimed %d expired session(s)", reaped)
        return reaped

    async def _reap_ephemeral_session(self, session_id: str) -> bool:
        """Delete a single ephemeral session + its room. Best-effort, idempotent."""
        try:
            # Reuse the existing session-delete path (leave channel + disconnect
            # + remove store record). This mirrors the client fast path exactly.
            await self.delete_session(session_id)
            logger.info("ephemeral reaper: reclaimed session %s", session_id)
            return True
        except SessionNotFoundError:
            # Not in the pool: the room may never have been loaded by this
            # instance, or it was already removed. Ensure the durable record is
            # gone so the room is not left tracked, then treat as reclaimed.
            try:
                await self._session_store.delete_session(session_id)
            except Exception as exc:  # best-effort
                logger.warning(
                    "ephemeral reaper: failed to delete store record for %s: %s",
                    session_id,
                    exc,
                )
                return False
            logger.info(
                "ephemeral reaper: removed stale store record for %s", session_id
            )
            return True
        except Exception as exc:  # best-effort: never crash the reaper loop
            logger.warning(
                "ephemeral reaper: failed to reap session %s: %s", session_id, exc
            )
            return False

    async def _ephemeral_reaper_loop(self) -> None:
        """Periodically reap expired ephemeral sessions until cancelled."""
        interval = self._ephemeral_reaper_interval_seconds
        logger.info(
            "Started ephemeral session reaper (ttl=%.0fs interval=%.0fs)",
            self._ephemeral_session_ttl_seconds,
            interval,
        )
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.reap_expired_ephemeral_sessions()
                except Exception as exc:  # best-effort: keep the loop alive
                    logger.warning("ephemeral reaper: cycle failed: %s", exc)
        except asyncio.CancelledError:
            logger.info("Ephemeral session reaper stopped")
            raise

    def start_ephemeral_reaper(self) -> None:
        """Start the background reaper task (idempotent)."""
        if self._reaper_task is not None and not self._reaper_task.done():
            return
        self._reaper_task = asyncio.create_task(self._ephemeral_reaper_loop())

    async def stop_ephemeral_reaper(self) -> None:
        """Stop the background reaper task if running."""
        task = self._reaper_task
        if task is None:
            return
        self._reaper_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ephemeral reaper: error during shutdown: %s", exc)
