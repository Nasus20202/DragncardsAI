"""
GameSession dataclass.

Represents a single active DragnCards game room with:
- A persistent WebSocket connection (PhoenixClient + Channel)
- Cached latest game state (updated on broadcasts)
- Metadata: session ID, plugin name, creation time, room slug
- Inbound event buffers: alerts (deque, maxlen=50), GUI updates (dict per player)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from game_service.phoenix_client.client import (
    Channel,
    PhoenixClient,
    PhoenixChannelError,
    PhxMessage,
)
from game_service.session.actions import GameAction, translate_action
from game_service.session.exceptions import (
    BadGameStateError,
    SessionError,
    StateUnavailableError,
)

logger = logging.getLogger(__name__)


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
    _manager: Any = field(
        default=None, init=False
    )  # back-reference set by SessionManager
    _state: Any = field(default=None, init=False)
    _state_stale: bool = field(default=False, init=False)
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _bad_state: bool = field(default=False, init=False)
    _state_unavailable: bool = field(default=False, init=False)
    _alerts: deque = field(default_factory=lambda: deque(maxlen=50), init=False)
    _gui_updates: dict = field(default_factory=dict, init=False)

    def __post_init__(self):
        # Subscribe to state broadcasts and cache them
        self.channel.on("current_state", self._on_full_state)
        # state_update carries a delta; we mark state as dirty to re-fetch on next read
        self.channel.on("state_update", self._on_delta)
        # Inbound error events
        self.channel.on("bad_game_state", self._on_bad_game_state)
        self.channel.on("unable_to_get_state_on_join", self._on_state_unavailable)
        self.channel.on("unable_to_get_state_on_request", self._on_state_unavailable)
        # Observable events
        self.channel.on("send_alert", self._on_alert)
        self.channel.on("gui_update", self._on_gui_update)

    # ------------------------------------------------------------------
    # Inbound event handlers
    # ------------------------------------------------------------------

    def _on_full_state(self, payload: Any) -> None:
        self._state = payload

    def _on_delta(self, payload: Any) -> None:
        # Mark state as stale so the next get_state() fetches fresh data.
        # We don't attempt to apply deltas client-side — DragnCards delta format
        # is complex and not officially documented.
        self._state_stale = True

    def _on_bad_game_state(self, payload: Any) -> None:
        logger.warning(
            "bad_game_state received for session %s: %s", self.session_id, payload
        )
        self._bad_state = True

    def _on_state_unavailable(self, payload: Any) -> None:
        logger.warning(
            "unable_to_get_state received for session %s: %s", self.session_id, payload
        )
        self._state_unavailable = True

    def _on_alert(self, payload: Any) -> None:
        self._alerts.append(payload)

    def _on_gui_update(self, payload: Any) -> None:
        player_n = payload.get("player_n") if isinstance(payload, dict) else None
        if player_n:
            self._gui_updates[player_n] = payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_state_flags(self) -> None:
        """Raise if the session has a persistent error flag set."""
        if self._bad_state:
            raise BadGameStateError(
                f"Session {self.session_id}: game state is corrupted or unavailable"
            )
        if self._state_unavailable:
            raise StateUnavailableError(
                f"Session {self.session_id}: game state is temporarily unavailable"
            )

    # ------------------------------------------------------------------
    # State access
    # ------------------------------------------------------------------

    async def execute_action(self, action: GameAction, timeout: float = 15.0) -> Any:
        """
        Translate and execute a game action, then return the resulting state.

        Sends a "game_action" message on the channel, waits for the state_update
        delta broadcast, requests the full state via request_state, and returns it.
        Raises SessionError if the action is rejected or times out.
        """
        self._check_state_flags()
        payload = translate_action(action)
        logger.info(
            "execute_action: session_id=%s payload=%r", self.session_id, payload
        )
        try:
            await self.channel.push("game_action", payload, timeout=timeout)
            await self.channel.wait_for_event(
                "state_update", "current_state", timeout=timeout
            )
            self._check_state_flags()
            await self.channel.push("request_state", {}, timeout=timeout)
            new_state = await self.channel.wait_for_state_update(timeout=timeout)
            self._check_state_flags()
            async with self._state_lock:
                self._state = new_state
                self._state_stale = False
            logger.info(
                "execute_action: session_id=%s -> state updated", self.session_id
            )
            return new_state
        except PhoenixChannelError as exc:
            logger.error(
                "execute_action: session_id=%s rejected: %s", self.session_id, exc
            )
            raise SessionError(f"Action rejected by DragnCards: {exc}") from exc
        except asyncio.TimeoutError as exc:
            logger.error("execute_action: session_id=%s timed out", self.session_id)
            raise SessionError(
                "Timed out waiting for state update after action"
            ) from exc

    async def get_state(self) -> Any:
        """Return the latest cached game state, re-fetching if stale or absent."""
        self._check_state_flags()
        async with self._state_lock:
            if self._state is None or self._state_stale:
                logger.info(
                    "get_state: session_id=%s fetching fresh state (stale=%s)",
                    self.session_id,
                    self._state_stale,
                )
                try:
                    await self.channel.push("request_state", {}, timeout=10.0)
                    self._state = await self.channel.wait_for_state_update(timeout=10.0)
                    self._state_stale = False
                except (PhoenixChannelError, asyncio.TimeoutError) as exc:
                    logger.error(
                        "get_state: session_id=%s failed: %s", self.session_id, exc
                    )
                    raise SessionError(f"Could not fetch game state: {exc}") from exc
            self._check_state_flags()
            return self._state

    # ------------------------------------------------------------------
    # Room control outbound methods
    # ------------------------------------------------------------------

    async def reset_game(
        self, save: bool = False, reload_plugin: bool = False, timeout: float = 15.0
    ) -> Any:
        """Reset the game, optionally reloading the plugin. Returns new state."""
        event = "reset_and_reload" if reload_plugin else "reset_game"
        logger.info(
            "reset_game: session_id=%s event=%s save=%s", self.session_id, event, save
        )
        try:
            await self.channel.push(
                event, {"options": {"save?": save}}, timeout=timeout
            )
            await self.channel.push("request_state", {}, timeout=timeout)
            new_state = await self.channel.wait_for_state_update(timeout=timeout)
            async with self._state_lock:
                self._state = new_state
                self._state_stale = False
                self._bad_state = False
            logger.info("reset_game: session_id=%s -> state updated", self.session_id)
            return new_state
        except PhoenixChannelError as exc:
            logger.error("reset_game: session_id=%s rejected: %s", self.session_id, exc)
            raise SessionError(f"reset_game rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            logger.error("reset_game: session_id=%s timed out", self.session_id)
            raise SessionError("Timed out waiting for state after reset") from exc

    async def set_seat(self, player_index: int, user_id: int) -> None:
        """Assign a user to a player seat (fire-and-forget — no phx_reply expected)."""
        timestamp = int(time.time() * 1000)
        msg = PhxMessage(
            join_ref=self.channel.join_ref,
            ref=self.client._next_ref(),
            topic=self.channel.topic,
            event="set_seat",
            payload={
                "player_i": player_index,
                "new_user_id": user_id,
                "timestamp": timestamp,
            },
        )
        await self.client._send(msg)

    async def set_spectator(self, user_id: int, spectating: bool) -> None:
        """Toggle spectator mode for a user (fire-and-forget — no phx_reply expected)."""
        msg = PhxMessage(
            join_ref=self.channel.join_ref,
            ref=self.client._next_ref(),
            topic=self.channel.topic,
            event="set_spectator",
            payload={"user_id": user_id, "value": spectating},
        )
        await self.client._send(msg)

    async def set_player_count(
        self,
        num_players: int,
        layout_id: str | None = None,
        timeout: float = 15.0,
    ) -> Any:
        """
        Set the number of players for this game room and return the resulting state.

        Sends a compound DragnLang action via game_action:
          ["SET", "/numPlayers", num_players]

        If layout_id is provided, also sends:
          ["SET_LAYOUT", "shared", layout_id]

        The layout ID is plugin-specific (e.g. "standard2Player" for Marvel Champions).
        If your plugin requires a layout change when altering player count, pass it here;
        otherwise the server will use whatever layout is currently active.

        Raises SessionError on timeout or channel rejection.
        """
        logger.info(
            "set_player_count: session_id=%s num_players=%s layout_id=%r",
            self.session_id,
            num_players,
            layout_id,
        )
        action_list: list = [["SET", "/numPlayers", num_players]]
        if layout_id is not None:
            action_list.append(["SET_LAYOUT", "shared", layout_id])

        description = f"Set player count to {num_players}"
        if layout_id is not None:
            description += f" (layout: {layout_id})"

        payload = {
            "action": "evaluate",
            "options": {
                "action_list": action_list,
                "description": description,
            },
            "timestamp": int(time.time() * 1000),
        }
        try:
            await self.channel.push("game_action", payload, timeout=timeout)
            await self.channel.wait_for_event(
                "state_update", "current_state", timeout=timeout
            )
            self._check_state_flags()
            await self.channel.push("request_state", {}, timeout=timeout)
            new_state = await self.channel.wait_for_state_update(timeout=timeout)
            self._check_state_flags()
            async with self._state_lock:
                self._state = new_state
                self._state_stale = False
            logger.info(
                "set_player_count: session_id=%s -> state updated", self.session_id
            )
            return new_state
        except PhoenixChannelError as exc:
            logger.error(
                "set_player_count: session_id=%s rejected: %s", self.session_id, exc
            )
            raise SessionError(f"set_player_count rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            logger.error("set_player_count: session_id=%s timed out", self.session_id)
            raise SessionError(
                "Timed out waiting for state after set_player_count"
            ) from exc

    async def close_room(self, timeout: float = 10.0) -> None:
        """Save and close the DragnCards room, then clean up this session from the pool."""
        try:
            await self.channel.push("close_room", {"options": {}}, timeout=timeout)
        except PhoenixChannelError as exc:
            raise SessionError(f"close_room rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for close_room ack") from exc
        finally:
            # Always clean up the pool entry — whether the push succeeded or not
            if self._manager is not None:
                try:
                    await self._manager._remove_session(self.session_id)
                except Exception:
                    pass

    async def send_alert(self, message: str, timeout: float = 10.0) -> None:
        """Broadcast an alert message to all participants in the room."""
        try:
            await self.channel.push("send_alert", {"message": message}, timeout=timeout)
        except PhoenixChannelError as exc:
            raise SessionError(f"send_alert rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for send_alert ack") from exc

    async def save_replay(self, timeout: float = 10.0) -> None:
        """Manually save the current replay."""
        timestamp = int(time.time() * 1000)
        try:
            await self.channel.push(
                "save_replay", {"options": {}, "timestamp": timestamp}, timeout=timeout
            )
        except PhoenixChannelError as exc:
            raise SessionError(f"save_replay rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for save_replay ack") from exc

    # ------------------------------------------------------------------
    # Observable event accessors
    # ------------------------------------------------------------------

    def get_alerts(self) -> list[dict]:
        """Return a copy of the buffered alerts."""
        return list(self._alerts)

    def get_gui_updates(self) -> dict[str, Any]:
        """Return a copy of the latest GUI update hints per player."""
        return dict(self._gui_updates)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def to_metadata(self) -> dict:
        """Return session metadata (no full state)."""
        return {
            "session_id": self.session_id,
            "plugin_name": self.plugin_name,
            "plugin_id": self.plugin_id,
            "room_slug": self.room_slug,
            "created_at": self.created_at.isoformat(),
        }
