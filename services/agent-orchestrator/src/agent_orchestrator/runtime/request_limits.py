from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

Scope = dict[str, Any]
Message = dict[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]


class MaxBodySizeMiddleware:
    """Reject oversized request bodies before the application buffers them.

    The ``conversation_context`` (and any other) body is validated only *after*
    the ASGI server has materialized the whole request in memory, so validation
    alone is not a resource-exhaustion boundary. This pure-ASGI middleware caps
    resident memory: it rejects a declared oversized ``Content-Length`` up front,
    and otherwise buffers the streamed body only up to ``max_bytes`` — returning
    ``413`` as soon as that ceiling is crossed — before the app is ever invoked.
    Within-limit bodies are replayed to the app unchanged.
    """

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
                # Client went away mid-send; hand the disconnect to the app so it
                # can observe it rather than swallowing the event here.
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
            # The body is fully delivered; defer to the real transport so the
            # app still observes later events (notably ``http.disconnect``, which
            # streaming/SSE handlers poll for to stop). Returning a synthetic
            # ``http.request`` here would hide the disconnect and hang the stream.
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
