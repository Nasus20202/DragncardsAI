from __future__ import annotations

import pytest

from agent_orchestrator.runtime.request_limits import MaxBodySizeMiddleware


class _Recorder:
    def __init__(self) -> None:
        self.status: int | None = None
        self.body = b""

    async def send(self, message: dict) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"") or b""


def _receive_from(chunks: list[tuple[bytes, bool]]):
    it = iter(chunks)

    async def receive() -> dict:
        try:
            body, more = next(it)
        except StopIteration:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": body, "more_body": more}

    return receive


async def _echo_app(scope: dict, receive, send) -> None:
    body = b""
    more = True
    while more:
        message = await receive()
        if message["type"] != "http.request":
            break
        body += message.get("body", b"") or b""
        more = message.get("more_body", False)
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": body})


@pytest.mark.asyncio
async def test_rejects_declared_oversized_content_length():
    mw = MaxBodySizeMiddleware(_echo_app, max_bytes=10)
    scope = {"type": "http", "headers": [(b"content-length", b"1000")]}
    rec = _Recorder()
    await mw(scope, _receive_from([(b"x" * 1000, False)]), rec.send)
    assert rec.status == 413


@pytest.mark.asyncio
async def test_rejects_streamed_body_over_limit_without_content_length():
    # No Content-Length header: the guard must still cap resident memory by
    # counting streamed bytes and rejecting once the ceiling is crossed.
    mw = MaxBodySizeMiddleware(_echo_app, max_bytes=10)
    scope = {"type": "http", "headers": []}
    rec = _Recorder()
    chunks = [(b"12345", True), (b"12345", True), (b"12345", False)]  # 15 > 10
    await mw(scope, _receive_from(chunks), rec.send)
    assert rec.status == 413


@pytest.mark.asyncio
async def test_passes_within_limit_body_to_app():
    mw = MaxBodySizeMiddleware(_echo_app, max_bytes=100)
    scope = {"type": "http", "headers": [(b"content-length", b"5")]}
    rec = _Recorder()
    await mw(scope, _receive_from([(b"hello", False)]), rec.send)
    assert rec.status == 200
    assert rec.body == b"hello"


@pytest.mark.asyncio
async def test_receive_after_body_surfaces_disconnect_to_app():
    # After the buffered body is delivered, further receive() calls must defer to
    # the real transport so streaming/SSE handlers still observe http.disconnect
    # (a synthetic http.request here would hang the stream).
    seen: dict[str, str] = {}

    async def app(scope: dict, receive, send) -> None:
        more = True
        while more:
            message = await receive()
            if message["type"] != "http.request":
                break
            more = message.get("more_body", False)
        seen["next"] = (await receive())["type"]
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    mw = MaxBodySizeMiddleware(app, max_bytes=100)
    rec = _Recorder()
    await mw({"type": "http", "headers": []}, _receive_from([(b"hi", False)]), rec.send)
    assert rec.status == 200
    assert seen["next"] == "http.disconnect"


@pytest.mark.asyncio
async def test_non_http_scope_passes_through():
    called: dict[str, bool] = {}

    async def app(scope: dict, receive, send) -> None:
        called["ok"] = True

    mw = MaxBodySizeMiddleware(app, max_bytes=10)
    await mw({"type": "lifespan"}, None, None)
    assert called.get("ok") is True
