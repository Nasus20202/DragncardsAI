from __future__ import annotations

import pytest
import httpx
from pydantic import ValidationError

from game_service.api.models import ChooseGameOptionRequest
from game_service.api.app import MAX_REQUEST_BODY_BYTES, create_app
from game_service.api.request_limits import MaxBodySizeMiddleware


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
async def test_rejects_declared_oversized_content_length_before_app():
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    middleware = MaxBodySizeMiddleware(app, max_bytes=10)
    recorder = _Recorder()
    await middleware(
        {"type": "http", "headers": [(b"content-length", b"1000")]},
        _receive_from([(b"x" * 1000, False)]),
        recorder.send,
    )

    assert recorder.status == 413
    assert not called


@pytest.mark.asyncio
async def test_rejects_streamed_body_over_limit_without_content_length():
    middleware = MaxBodySizeMiddleware(_echo_app, max_bytes=10)
    recorder = _Recorder()
    await middleware(
        {"type": "http", "headers": []},
        _receive_from([(b"12345", True), (b"12345", True), (b"12345", False)]),
        recorder.send,
    )

    assert recorder.status == 413


@pytest.mark.asyncio
async def test_passes_within_limit_body_to_app():
    middleware = MaxBodySizeMiddleware(_echo_app, max_bytes=100)
    recorder = _Recorder()
    await middleware(
        {"type": "http", "headers": [(b"content-length", b"5")]},
        _receive_from([(b"hello", False)]),
        recorder.send,
    )

    assert recorder.status == 200
    assert recorder.body == b"hello"


def test_choice_request_bounds_identifiers_and_selection_lengths():
    valid = {
        "option_id": "option-1",
        "targets": [1, "target-1"],
        "resources": [2],
        "prompt_id": "player1:1",
        "prompt_version": 1,
    }
    assert ChooseGameOptionRequest.model_validate(valid).option_id == "option-1"

    oversized = (
        ("option_id", "x" * 129),
        ("prompt_id", "x" * 129),
        ("prompt_version", 2**32),
        ("targets", list(range(33))),
        ("resources", list(range(33))),
        ("targets", ["x" * 129]),
        ("resources", ["x" * 129]),
    )
    for field, value in oversized:
        with pytest.raises(ValidationError):
            ChooseGameOptionRequest.model_validate({**valid, field: value})


@pytest.mark.asyncio
async def test_game_app_rejects_oversized_body_before_json_parsing():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.post(
            "/games",
            content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
