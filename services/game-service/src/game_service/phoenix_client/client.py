"""
Phoenix Channels WebSocket client.

Implements the Phoenix Channels protocol:
- Message format: [join_ref, ref, topic, event, payload]
- Heartbeat: periodic phoenix/heartbeat messages
- Channel join/leave with reply handling
- Push/receive with await-response pattern
- Connection loss detection and reconnection
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)

# Phoenix sentinel values
_NULL = None  # join_ref / ref when not applicable


@dataclass
class PhxMessage:
    """A decoded Phoenix Channels message."""

    join_ref: str | None
    ref: str | None
    topic: str
    event: str
    payload: Any

    @classmethod
    def decode(cls, raw: str) -> "PhxMessage":
        parts = json.loads(raw)
        return cls(
            join_ref=parts[0],
            ref=parts[1],
            topic=parts[2],
            event=parts[3],
            payload=parts[4],
        )

    def encode(self) -> str:
        return json.dumps(
            [self.join_ref, self.ref, self.topic, self.event, self.payload]
        )


class PhoenixChannelError(Exception):
    """Raised when a channel operation fails."""


class PhoenixClient:
    """
    Async Phoenix Channels WebSocket client.

    Usage::

        client = PhoenixClient("ws://localhost:4000/socket", auth_token="...")
        await client.connect()
        channel = await client.join("room:my-room")
        reply = await channel.push("game_action", {"action": ..., "options": {}, "timestamp": 0})
        await client.disconnect()
    """

    HEARTBEAT_INTERVAL = 30  # seconds
    RECONNECT_DELAY = 2  # seconds
    MAX_RECONNECT_ATTEMPTS = 5

    def __init__(self, url: str, auth_token: str | None = None):
        # Append token to URL as query param (Phoenix socket convention)
        sep = "&" if "?" in url else "?"
        self._url = f"{url}/websocket{sep}vsn=2.0.0" + (
            f"&authToken={auth_token}" if auth_token else ""
        )
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._ref_counter = 0
        self._pending: dict[str, asyncio.Future] = {}  # ref -> Future
        self._channels: dict[str, "Channel"] = {}  # topic -> Channel
        self._recv_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._connected = asyncio.Event()
        self._closed = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the WebSocket connection and start background tasks."""
        self._ws = await websockets.connect(self._url)
        self._connected.set()
        self._closed = False
        self._recv_task = asyncio.create_task(self._recv_loop(), name="phx-recv")
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="phx-heartbeat"
        )
        logger.debug("PhoenixClient connected to %s", self._url)

    async def disconnect(self) -> None:
        """Close the WebSocket and cancel background tasks."""
        self._closed = True
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._recv_task:
            self._recv_task.cancel()
        if self._ws:
            await self._ws.close()
        self._connected.clear()
        logger.debug("PhoenixClient disconnected")

    # ------------------------------------------------------------------
    # Channel operations
    # ------------------------------------------------------------------

    async def join(self, topic: str, payload: Any = None) -> "Channel":
        """Join a Phoenix channel topic and return a Channel handle."""
        join_ref = self._next_ref()
        ref = self._next_ref()
        msg = PhxMessage(
            join_ref=join_ref,
            ref=ref,
            topic=topic,
            event="phx_join",
            payload=payload or {},
        )
        reply = await self._push_and_await(msg, reply_ref=ref)
        if reply.payload.get("status") != "ok":
            raise PhoenixChannelError(f"Failed to join {topic!r}: {reply.payload}")
        channel = Channel(topic=topic, join_ref=join_ref, client=self)
        self._channels[topic] = channel
        logger.debug("Joined channel %s", topic)
        return channel

    async def leave(self, topic: str) -> None:
        """Leave a Phoenix channel topic."""
        if topic not in self._channels:
            return
        channel = self._channels.pop(topic)
        ref = self._next_ref()
        msg = PhxMessage(
            join_ref=channel.join_ref,
            ref=ref,
            topic=topic,
            event="phx_leave",
            payload={},
        )
        try:
            await self._push_and_await(msg, reply_ref=ref, timeout=5.0)
        except (asyncio.TimeoutError, PhoenixChannelError):
            pass  # Best-effort leave
        logger.debug("Left channel %s", topic)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_ref(self) -> str:
        self._ref_counter += 1
        return str(self._ref_counter)

    async def _send(self, msg: PhxMessage) -> None:
        if self._ws is None:
            raise PhoenixChannelError("Not connected")
        await self._ws.send(msg.encode())

    async def _push_and_await(
        self, msg: PhxMessage, reply_ref: str, timeout: float = 10.0
    ) -> PhxMessage:
        """Send a message and wait for a phx_reply with matching ref."""
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[reply_ref] = future
        try:
            await self._send(msg)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(reply_ref, None)
            raise
        except Exception:
            self._pending.pop(reply_ref, None)
            raise

    async def _recv_loop(self) -> None:
        """Background task: read messages and dispatch them."""
        try:
            assert self._ws is not None
            async for raw in self._ws:
                try:
                    msg = PhxMessage.decode(raw)
                    self._dispatch(msg)
                except Exception as exc:
                    logger.warning("Error decoding message %r: %s", raw, exc)
        except (ConnectionClosed, asyncio.CancelledError):
            pass
        except Exception as exc:
            logger.error("recv_loop error: %s", exc)
        finally:
            self._connected.clear()
            if not self._closed:
                logger.warning("Connection lost, scheduling reconnect")
                asyncio.create_task(self._reconnect())

    def _dispatch(self, msg: PhxMessage) -> None:
        """Route an incoming message to a pending future or channel handler."""
        if msg.event == "phx_reply" and msg.ref in self._pending:
            future = self._pending.pop(msg.ref)
            if not future.done():
                future.set_result(msg)
            return
        # Dispatch to channel
        channel = self._channels.get(msg.topic)
        if channel:
            channel._handle(msg)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeat messages (required by Phoenix)."""
        try:
            while True:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                ref = self._next_ref()
                msg = PhxMessage(
                    join_ref=_NULL,
                    ref=ref,
                    topic="phoenix",
                    event="heartbeat",
                    payload={},
                )
                try:
                    await self._push_and_await(msg, reply_ref=ref, timeout=5.0)
                    logger.debug("Heartbeat OK (ref=%s)", ref)
                except (asyncio.TimeoutError, PhoenixChannelError) as exc:
                    logger.warning("Heartbeat failed: %s", exc)
        except asyncio.CancelledError:
            pass

    async def _reconnect(self) -> None:
        """Attempt to reconnect after connection loss."""
        for attempt in range(1, self.MAX_RECONNECT_ATTEMPTS + 1):
            logger.info("Reconnect attempt %d/%d", attempt, self.MAX_RECONNECT_ATTEMPTS)
            await asyncio.sleep(self.RECONNECT_DELAY * attempt)
            try:
                await self.connect()
                # Rejoin all previously joined channels
                for topic, channel in list(self._channels.items()):
                    try:
                        await self.join(topic)
                        logger.info("Rejoined channel %s after reconnect", topic)
                    except Exception as exc:
                        logger.error("Failed to rejoin %s: %s", topic, exc)
                return
            except Exception as exc:
                logger.warning("Reconnect attempt %d failed: %s", attempt, exc)
        logger.error("All reconnect attempts exhausted — session degraded")


@dataclass
class Channel:
    """
    Handle for a joined Phoenix channel.

    Provides push() to send events and subscribe() to receive broadcasts.
    """

    topic: str
    join_ref: str
    client: PhoenixClient
    _handlers: dict[str, list] = field(default_factory=dict, init=False)
    _state_queue: asyncio.Queue = field(default_factory=asyncio.Queue, init=False)

    async def push(self, event: str, payload: Any, timeout: float = 10.0) -> Any:
        """Push an event on this channel and await the reply payload."""
        ref = self.client._next_ref()
        msg = PhxMessage(
            join_ref=self.join_ref,
            ref=ref,
            topic=self.topic,
            event=event,
            payload=payload,
        )
        reply = await self.client._push_and_await(msg, reply_ref=ref, timeout=timeout)
        if reply.payload.get("status") == "error":
            raise PhoenixChannelError(
                f"Action rejected: {reply.payload.get('response')}"
            )
        return reply.payload.get("response", reply.payload)

    def on(self, event: str, handler) -> None:
        """Register a broadcast handler for the given event."""
        self._handlers.setdefault(event, []).append(handler)

    def _handle(self, msg: PhxMessage) -> None:
        """Dispatch an incoming broadcast to registered handlers."""
        handlers = self._handlers.get(msg.event, [])
        for h in handlers:
            try:
                h(msg.payload)
            except Exception as exc:
                logger.warning("Handler error for event %s: %s", msg.event, exc)
        # Queue state-update events for consumption by callers.
        # - current_state: full state broadcast (on join or after request_state)
        # - state_update:  delta broadcast sent after game_action (DragnCards v2 API)
        # - send_update:   legacy alias kept for compatibility
        if msg.event in ("current_state", "state_update", "send_update"):
            try:
                self._state_queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    async def wait_for_event(self, *events: str, timeout: float = 15.0) -> PhxMessage:
        """Block until any of the named events is broadcast on this channel."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise asyncio.TimeoutError
            try:
                msg = await asyncio.wait_for(self._state_queue.get(), timeout=remaining)
                if msg.event in events:
                    return msg
                # Put it back if it's not the event we want
                self._state_queue.put_nowait(msg)
                await asyncio.sleep(0.01)
            except asyncio.QueueFull:
                await asyncio.sleep(0.01)

    async def wait_for_state_update(self, timeout: float = 15.0) -> Any:
        """Block until a full current_state is broadcast on this channel."""
        msg = await self.wait_for_event("current_state", timeout=timeout)
        return msg.payload
