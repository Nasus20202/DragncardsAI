"""Render-frame WebSocket transport and prompt liveness guards."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode, urlsplit, urlunsplit

import websockets

from game_service.logic.exceptions import SessionError
from game_service.telemetry import get_tracer

tracer = get_tracer(__name__)

PERMITTED_DRIVER_TELEMETRY_ATTRIBUTE_KEYS = frozenset(
    {
        "game.platform",
        "game.seat",
        "game.action.name",
        "game.seat.count",
        "game.attempt",
        "game.outcome",
        "error.type",
        "game.hero.count",
        "game.encounter_set.count",
        "game.option.count",
        "game.prompt.present",
        "game.option.id",
        "game.target.count",
        "game.resource.count",
        "http.request.method",
        "http.route",
    }
)

PERMITTED_SOCKET_TELEMETRY_ATTRIBUTE_KEYS = frozenset(
    {
        "game.platform",
        "game.seat",
        "game.seat.count",
        "game.attempt",
        "game.outcome",
        "error.type",
    }
)


class StuckPromptError(SessionError):
    """The engine repeated a prompt after bounded submissions."""


@dataclass(frozen=True)
class FrameDescriptor:
    render_id: int
    game_id: int
    ask_players: tuple[int, ...]
    remaining_time: float
    max_timeout: float
    notify_texts: tuple[Any, ...]
    debug_message: str
    current_step_id: int
    max_replay_step_id: int
    player_id: int
    total_players: int
    transport_error: str | None = None

    @classmethod
    def from_payload(cls, payload: str | bytes | dict[str, Any]) -> "FrameDescriptor":
        if isinstance(payload, (str, bytes, bytearray)):
            payload = json.loads(payload)
        if not isinstance(payload, dict):
            raise ValueError("marvel-lcg render frame is not an object")
        notifications: list[Any] = []
        for item in payload.get("notify_texts") or []:
            if isinstance(item, str):
                try:
                    notifications.append(json.loads(item))
                except (ValueError, TypeError) as exc:
                    raise ValueError("marvel-lcg notify_text is not JSON") from exc
            else:
                notifications.append(item)
        return cls(
            render_id=int(payload.get("render_id", 0)),
            game_id=int(payload.get("game_id", 0)),
            ask_players=tuple(int(item) for item in payload.get("ask_players") or []),
            remaining_time=float(payload.get("remaining_time", 0)),
            max_timeout=float(payload.get("max_timeout", 0)),
            notify_texts=tuple(notifications),
            debug_message=str(payload.get("debug_message", "")),
            current_step_id=int(payload.get("current_step_id", 0)),
            max_replay_step_id=int(payload.get("max_replay_step_id", 0)),
            player_id=int(payload.get("player_id", 0)),
            total_players=int(payload.get("total_players", 0)),
        )

    @property
    def game_over(self) -> bool:
        return self.render_id == -1 and self.transport_error is None

    @property
    def transport_degraded(self) -> bool:
        return self.transport_error is not None


class FrameBuffer:
    """Coalesce a burst of frames into the latest frame."""

    def __init__(self) -> None:
        self.latest: FrameDescriptor | None = None
        self._changed = asyncio.Event()

    def put(self, frame: FrameDescriptor) -> None:
        self.latest = frame
        self._changed.set()

    async def get(self, timeout: float | None = None) -> FrameDescriptor:
        waiter = self._changed.wait()
        if timeout is None:
            await waiter
        else:
            await asyncio.wait_for(waiter, timeout=timeout)
        self._changed.clear()
        if self.latest is None:  # pragma: no cover - defensive
            raise RuntimeError("frame buffer signalled without a frame")
        return self.latest


@dataclass(frozen=True)
class PromptSignature:
    render_id: int
    ask_players: tuple[int, ...]
    prompt_text: str
    option_ids: tuple[str, ...]


class PromptAttemptGuard:
    """Bound submissions and identify a recurring complete prompt tuple."""

    def __init__(self, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.max_attempts = max_attempts
        self._attempts: dict[PromptSignature, list[str]] = {}

    def record(self, signature: PromptSignature, option_id: int | str) -> None:
        attempted = self._attempts.setdefault(signature, [])
        attempted.append(str(option_id))

    def attempts(self, signature: PromptSignature) -> int:
        return len(self._attempts.get(signature, []))

    def attempted_options(self, signature: PromptSignature) -> list[str]:
        return list(self._attempts.get(signature, []))

    def raise_if_exhausted(self, signature: PromptSignature) -> None:
        attempted = self._attempts.get(signature, [])
        if len(attempted) >= self.max_attempts:
            raise StuckPromptError(
                f"marvel-lcg prompt remained after {len(attempted)} attempts"
            )

    def clear_except(self, signature: PromptSignature | None) -> None:
        if signature is None:
            self._attempts.clear()
        else:
            self._attempts = (
                {signature: self._attempts[signature]}
                if signature in self._attempts
                else {}
            )

    def clear(self, signature: PromptSignature) -> None:
        self._attempts.pop(signature, None)


class MarvelLcgRenderSocket:
    """One-seat render socket with handshake, frame coalescing and reconnect."""

    def __init__(
        self,
        url: str,
        *,
        seat: int,
        cookie_header: str = "",
        handshake_url: str | None = None,
        websocket_factory: Callable[..., Awaitable[Any]] | None = None,
        on_frame: Callable[[FrameDescriptor], Awaitable[None] | None] | None = None,
        reconnect_attempts: int = 3,
        reconnect_delay: float = 0.05,
    ) -> None:
        self.url = self._with_seat(url, seat)
        self.seat = seat
        self.cookie_header = cookie_header
        self.handshake_url = handshake_url or self.url.rsplit("/ws", 1)[0] + "/"
        self.websocket_factory = websocket_factory or websockets.connect
        self.on_frame = on_frame
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.frames = FrameBuffer()
        self._socket: Any = None
        self._reader_task: asyncio.Task[None] | None = None
        self._closed = False

    @staticmethod
    def _with_seat(url: str, seat: int) -> str:
        parsed = urlsplit(url)
        query = dict()
        if parsed.query:
            query.update(
                item.split("=", 1) for item in parsed.query.split("&") if "=" in item
            )
        query["p"] = str(seat)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )

    async def _open_socket(self) -> Any:
        headers = {"Cookie": self.cookie_header} if self.cookie_header else {}
        try:
            return await self.websocket_factory(
                self.url, additional_headers=headers or None
            )
        except TypeError:
            # websockets < 14 called this argument ``extra_headers``; keeping the
            # fallback makes the transport easy to test with small fakes too.
            return await self.websocket_factory(self.url, extra_headers=headers or None)

    async def _publish_frame(self, frame: FrameDescriptor) -> None:
        """Publish an incoming frame and notify the platform callback."""
        self.frames.put(frame)
        if self.on_frame is None:
            return
        try:
            result = self.on_frame(frame)
            if hasattr(result, "__await__"):
                await result
        except Exception:
            # Frame callbacks are observers; a failed history/state
            # projection must not tear down the transport reader.
            pass

    async def _announce_connection(self, socket: Any) -> None:
        """Send the client handshake announcement under its own span."""
        with tracer.start_as_current_span(
            "marvel_lcg.socket.announce",
            attributes={
                "game.platform": "marvel-lcg",
                "game.seat": self.seat,
                "game.outcome": "sending",
            },
        ) as span:
            try:
                await socket.send(f"Connected {self.handshake_url}")
            except Exception as exc:
                span.set_attribute("game.outcome", "failed")
                span.set_attribute("error.type", type(exc).__name__)
                raise
            span.set_attribute("game.outcome", "sent")

    async def open(self) -> None:
        self._closed = False
        self._socket = await self._open_socket()
        await self._announce_connection(self._socket)
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _reconnect(self) -> None:
        for attempt in range(self.reconnect_attempts):
            if self._closed:
                return
            try:
                with tracer.start_as_current_span(
                    "marvel_lcg.socket.reconnect",
                    attributes={
                        "game.platform": "marvel-lcg",
                        "game.seat": self.seat,
                        "game.attempt": attempt + 1,
                    },
                ) as span:
                    try:
                        self._socket = await self._open_socket()
                        await self._announce_connection(self._socket)
                    except Exception as exc:
                        span.set_attribute("game.outcome", "failed")
                        span.set_attribute("error.type", type(exc).__name__)
                        raise
                    span.set_attribute("game.outcome", "reconnected")
                return
            except Exception:
                if attempt + 1 >= self.reconnect_attempts:
                    raise
                await asyncio.sleep(self.reconnect_delay * (attempt + 1))

    async def _read_loop(self) -> None:
        while not self._closed:
            try:
                raw = await self._socket.recv()
                if raw is None:
                    raise ConnectionError("marvel-lcg render socket closed")
                frame = FrameDescriptor.from_payload(raw)
                await self._publish_frame(frame)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                with tracer.start_as_current_span(
                    "marvel_lcg.socket.unexpected_close",
                    attributes={
                        "game.platform": "marvel-lcg",
                        "game.seat": self.seat,
                        "game.outcome": "unexpected_close",
                        "error.type": type(exc).__name__,
                    },
                ):
                    pass
                if self._closed:
                    return
                try:
                    await self._reconnect()
                except Exception as reconnect_exc:
                    with tracer.start_as_current_span(
                        "marvel_lcg.socket.reconnect_exhausted",
                        attributes={
                            "game.platform": "marvel-lcg",
                            "game.seat": self.seat,
                            "game.attempt": self.reconnect_attempts,
                            "game.outcome": "degraded",
                            "error.type": type(reconnect_exc).__name__,
                        },
                    ):
                        pass
                    await self._publish_frame(
                        FrameDescriptor(
                            render_id=-1,
                            game_id=0,
                            ask_players=(),
                            remaining_time=0,
                            max_timeout=0,
                            notify_texts=(
                                {"error": "render socket reconnect exhausted"},
                            ),
                            debug_message="render socket reconnect exhausted",
                            current_step_id=0,
                            max_replay_step_id=0,
                            player_id=self.seat,
                            total_players=0,
                            transport_error="render socket reconnect exhausted",
                        )
                    )
                    return

    async def wait_for_frame(self, timeout: float | None = None) -> FrameDescriptor:
        return await self.frames.get(timeout)

    async def close(self) -> None:
        with tracer.start_as_current_span(
            "marvel_lcg.socket.disconnect",
            attributes={
                "game.platform": "marvel-lcg",
                "game.seat": self.seat,
                "game.outcome": "closed",
            },
        ):
            self._closed = True
            if self._reader_task is not None:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except asyncio.CancelledError:
                    pass
                self._reader_task = None
            if self._socket is not None:
                close = getattr(self._socket, "close", None)
                if close is not None:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result
                self._socket = None


MarvelLcgWebSocket = MarvelLcgRenderSocket
RenderFrameDescriptor = FrameDescriptor
