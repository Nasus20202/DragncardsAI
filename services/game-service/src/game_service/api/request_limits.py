"""Pure-ASGI request body limits for the game-service."""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class MaxBodySizeMiddleware:
    """Reject oversized bodies before FastAPI parses JSON or form data."""

    def __init__(self, app: Any, *, max_bytes: int):
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        declared = _declared_content_length(scope)
        if declared is not None and declared > self._max_bytes:
            await self._reject(send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":

                async def _disconnected() -> Message:
                    return message

                await self._app(scope, _disconnected, send)
                return
            body.extend(message.get("body", b"") or b"")
            more_body = message.get("more_body", False)
            if len(body) > self._max_bytes:
                await self._reject(send)
                return

        buffered = bytes(body)
        sent = False

        async def replay() -> Message:
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": buffered,
                    "more_body": False,
                }
            return await receive()

        await self._app(scope, replay, send)

    async def _reject(self, send: Send) -> None:
        payload = json.dumps({"detail": "Request body too large"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def _declared_content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or []:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None
