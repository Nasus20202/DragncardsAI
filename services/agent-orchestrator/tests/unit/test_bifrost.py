from __future__ import annotations

import json
from time import monotonic

import httpx
import pytest

from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError


class FakeValkeyCache:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[object, float | None]] = {}

    async def get_json(self, key: str):
        entry = self._entries.get(key)
        if entry is None:
            return None
        payload, expires_at = entry
        if expires_at is not None and expires_at <= monotonic():
            self._entries.pop(key, None)
            return None
        return payload

    async def set_json(self, key: str, value: object, ttl_seconds: float):
        expires_at = monotonic() + ttl_seconds if ttl_seconds > 0 else None
        self._entries[key] = (value, expires_at)


async def _build_client(
    handler, *, api_key: str = "", model_cache=None
) -> BifrostClient:
    client = BifrostClient(
        "http://bifrost",
        api_key,
        {"openai": "openai", "openrouter": "openrouter"},
        model_cache=model_cache,
    )
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_resolve_model_uses_provider_prefixes():
    client = BifrostClient(
        "http://bifrost", "", {"openai": "openai", "openrouter": "openrouter"}
    )

    assert client._resolve_model("openai", "gpt-4o-mini") == "gpt-4o-mini"
    assert (
        client._resolve_model("openrouter", "gpt-4o-mini") == "openrouter/gpt-4o-mini"
    )
    assert (
        client._resolve_model("openrouter", "custom/provider-model")
        == "custom/provider-model"
    )


def test_normalize_content_supports_openai_shapes():
    client = BifrostClient("http://bifrost", "", {"openai": "openai"})

    assert client._normalize_content(None) == ""
    assert client._normalize_content("hello") == "hello"
    assert (
        client._normalize_content(
            [
                {"type": "text", "text": "alpha"},
                {"type": "ignored", "text": "beta"},
                {"type": "text", "text": "gamma"},
            ]
        )
        == "alpha\ngamma"
    )
    assert client._normalize_content(123) == "123"


def test_extract_error_message_prefers_nested_message():
    client = BifrostClient("http://bifrost", "", {"openai": "openai"})
    request = httpx.Request("GET", "http://bifrost/openai/v1/models")
    response = httpx.Response(
        502,
        json={"error": {"message": "gateway exploded"}},
        request=request,
    )

    assert client._extract_error_message(response) == "gateway exploded"


@pytest.mark.asyncio
async def test_list_models_parses_response_payload():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-bf-list-models-provider"] == "openrouter"
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "openrouter/gpt-4o-mini",
                        "name": "GPT-4o mini",
                        "supported_methods": ["chat_completion"],
                    },
                    {"id": "openrouter/o3-mini", "supported_methods": []},
                    "ignored",
                ]
            },
            request=request,
        )

    client = await _build_client(handler, api_key="secret")
    try:
        models = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert [model.id for model in models] == [
        "openrouter/gpt-4o-mini",
        "openrouter/o3-mini",
    ]
    assert models[0].name == "GPT-4o mini"


@pytest.mark.asyncio
async def test_list_models_raises_gateway_error_for_http_failure():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            502, json={"error": {"message": "provider down"}}, request=request
        )

    client = await _build_client(handler)
    try:
        with pytest.raises(BifrostError) as exc_info:
            await client.list_models("openai")
    finally:
        await client.aclose()

    assert exc_info.value.code == "gateway_error"
    assert exc_info.value.retryable is True
    assert str(exc_info.value) == "provider down"


@pytest.mark.asyncio
async def test_list_models_raises_timeout_for_request_timeout():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client = await _build_client(handler)
    try:
        with pytest.raises(BifrostError) as exc_info:
            await client.list_models("openai")
    finally:
        await client.aclose()

    assert exc_info.value.code == "timeout"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_get_model_context_length_returns_none_when_fetch_all_models_fails():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "down"}}, request=request)

    client = await _build_client(handler)
    try:
        context_length = await client.get_model_context_length("openai", "gpt-4o-mini")
    finally:
        await client.aclose()

    assert context_length is None


@pytest.mark.asyncio
async def test_chat_completion_parses_tool_calls():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = request.content.decode("utf-8")
        assert "openrouter/gpt-4o-mini" in payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": [{"type": "text", "text": "hello"}],
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "demo_tool",
                                        "arguments": '{"count": 2}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openrouter",
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            [{"type": "function", "function": {"name": "demo_tool", "parameters": {}}}],
            {},
            {},
        )
    finally:
        await client.aclose()

    assert response.content == "hello"
    assert response.tool_calls[0].name == "demo_tool"
    assert response.tool_calls[0].arguments == {"count": 2}


@pytest.mark.asyncio
async def test_chat_completion_raises_invalid_response_for_missing_choices():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []}, request=request)

    client = await _build_client(handler)
    try:
        with pytest.raises(BifrostError) as exc_info:
            await client.chat_completion("openai", "gpt-4o-mini", [], None, {}, {})
    finally:
        await client.aclose()

    assert exc_info.value.code == "invalid_response"


@pytest.mark.asyncio
async def test_chat_completion_streams_reasoning_and_content_deltas():
    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text="\n\n".join(
                [
                    'data: {"choices":[{"delta":{"reasoning_details":[{"index":0,"type":"text","text":"Let me think. "}]},"finish_reason":null}]}',
                    'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
                    'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
                    "data: [DONE]",
                ]
            ),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    deltas = []
    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openrouter",
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            None,
            {"reasoning": {"effort": "high"}},
            {},
            on_delta=deltas.append,
        )
    finally:
        await client.aclose()

    assert [delta.reasoning for delta in deltas if delta.reasoning] == [
        "Let me think. "
    ]
    assert [delta.content for delta in deltas if delta.content] == ["Hello", " world"]
    assert response.reasoning == "Let me think. "
    assert response.content == "Hello world"
    assert response.reasoning_details[0].text == "Let me think. "


@pytest.mark.asyncio
async def test_chat_completion_stream_parses_tool_call_deltas_without_callback_invocation():
    deltas = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["stream"] is True
        return httpx.Response(
            200,
            text="\n\n".join(
                [
                    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call-1","function":{"name":"demo_","arguments":"{\\"count\\":"}}]},"finish_reason":null}]}',
                    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"name":"tool","arguments":" 2}"}}]},"finish_reason":null}]}',
                    "data: [DONE]",
                ]
            ),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai",
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            [{"type": "function", "function": {"name": "demo_tool", "parameters": {}}}],
            {},
            {},
            on_delta=deltas.append,
        )
    finally:
        await client.aclose()

    assert deltas == []
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].id == "call-1"
    assert response.tool_calls[0].name == "demo_tool"
    assert response.tool_calls[0].arguments == {"count": 2}


@pytest.mark.asyncio
async def test_chat_completion_parses_invalid_tool_call_arguments_as_raw_string():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "hello",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "function": {
                                        "name": "demo_tool",
                                        "arguments": "{not-json}",
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai",
            "gpt-4o-mini",
            [{"role": "user", "content": "hi"}],
            None,
            {},
            {},
        )
    finally:
        await client.aclose()

    assert response.tool_calls[0].arguments == {"raw": "{not-json}"}


@pytest.mark.asyncio
async def test_list_models_uses_valkey_cache_within_ttl():
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": f"openrouter/model-{call_count}", "supported_methods": []}
                ]
            },
            request=request,
        )

    cache = FakeValkeyCache()
    client = await _build_client(handler, model_cache=cache)
    client._models_cache_ttl_seconds = 60.0
    try:
        first = await client.list_models("openrouter")
        second = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 1
    assert [model.id for model in first] == ["openrouter/model-1"]
    assert [model.id for model in second] == ["openrouter/model-1"]


@pytest.mark.asyncio
async def test_list_models_refreshes_cache_after_ttl_expiry():
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": f"openrouter/model-{call_count}", "supported_methods": []}
                ]
            },
            request=request,
        )

    cache = FakeValkeyCache()
    client = await _build_client(handler, model_cache=cache)
    client._models_cache_ttl_seconds = 0.01
    try:
        first = await client.list_models("openrouter")
        await __import__("asyncio").sleep(0.02)
        second = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 2
    assert [model.id for model in first] == ["openrouter/model-1"]
    assert [model.id for model in second] == ["openrouter/model-2"]


@pytest.mark.asyncio
async def test_list_models_routes_lmstudio_through_bifrost():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://bifrost/openai/v1/models")
        assert request.headers.get("x-bf-list-models-provider") == "lmstudio"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "lmstudio/qwen3.5-0.8b",
                        "name": "qwen3.5-0.8b",
                    }
                ]
            },
            request=request,
        )

    client = BifrostClient(
        "http://bifrost",
        "",
        {"openai": "openai", "lmstudio": "lmstudio"},
    )
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        models = await client.list_models("lmstudio")
    finally:
        await client.aclose()

    assert [model.id for model in models] == ["lmstudio/qwen3.5-0.8b"]


@pytest.mark.asyncio
async def test_chat_completion_routes_lmstudio_through_bifrost():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://bifrost/openai/chat/completions")
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["model"] == "lmstudio/qwen3.5-0.8b"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Hello there!",
                            "tool_calls": [],
                        }
                    }
                ]
            },
            request=request,
        )

    client = BifrostClient(
        "http://bifrost",
        "",
        {"openai": "openai", "lmstudio": "lmstudio"},
    )
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        response = await client.chat_completion(
            "lmstudio",
            "qwen3.5-0.8b",
            [{"role": "user", "content": "hi"}],
            None,
            {},
            {},
        )
    finally:
        await client.aclose()

    assert response.content == "Hello there!"
