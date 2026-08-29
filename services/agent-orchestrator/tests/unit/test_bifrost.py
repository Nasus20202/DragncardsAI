from __future__ import annotations

import json

import httpx
import pytest

from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError
from agent_orchestrator.storage.valkey import RespConnection

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _build_client(
    handler, *, api_key: str = "", valkey: RespConnection | None = None
) -> BifrostClient:
    client = BifrostClient(
        "http://bifrost",
        api_key,
        {"openai": "openai", "openrouter": "openrouter"},
        valkey=valkey,
    )
    await client._http_client.aclose()
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


class _FakeValkey:
    """Minimal in-process stand-in for _RespConnection (GET/SETEX/DEL)."""

    def __init__(self):
        self._store: dict[str, str] = {}
        self.get_calls: list[str] = []
        self.set_calls: list[tuple[str, str]] = []
        self.setex_calls: list[tuple[str, int, str]] = []
        self.del_calls: list[tuple[str, ...]] = []

    async def execute(self, *parts: object):
        command = str(parts[0]).upper()
        if command == "GET":
            key = str(parts[1])
            self.get_calls.append(key)
            return self._store.get(key)
        if command == "SETEX":
            key = str(parts[1])
            # parts[2] is TTL, parts[3] is value
            ttl = int(str(parts[2]))
            value = str(parts[3])
            self.set_calls.append((key, value))
            self.setex_calls.append((key, ttl, value))
            self._store[key] = value
            return "OK"
        if command == "DEL":
            keys = tuple(str(part) for part in parts[1:])
            self.del_calls.append(keys)
            removed = 0
            for key in keys:
                if self._store.pop(key, None) is not None:
                    removed += 1
            return removed
        raise RuntimeError(f"_FakeValkey: unsupported command {command!r}")


class _ErrorValkey:
    """Always raises on execute — used to test error fall-through."""

    async def execute(self, *parts: object):
        raise OSError("connection refused")


# ---------------------------------------------------------------------------
# Existing tests (unchanged behaviour)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Valkey cache tests (tasks 4.1–4.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_get_returns_none_on_miss():
    valkey = _FakeValkey()
    client = BifrostClient("http://bifrost", "", {"openai": "openai"}, valkey=valkey)
    result = await client._cache_get("missing-key")
    assert result is None
    assert valkey.get_calls == ["missing-key"]


@pytest.mark.asyncio
async def test_cache_get_returns_data_on_hit():
    valkey = _FakeValkey()
    valkey._store["my-key"] = json.dumps([{"id": "m1"}])
    client = BifrostClient("http://bifrost", "", {"openai": "openai"}, valkey=valkey)
    result = await client._cache_get("my-key")
    assert result == [{"id": "m1"}]


@pytest.mark.asyncio
async def test_cache_get_returns_none_on_valkey_error():
    client = BifrostClient(
        "http://bifrost", "", {"openai": "openai"}, valkey=_ErrorValkey()
    )
    # Must not raise
    result = await client._cache_get("some-key")
    assert result is None


@pytest.mark.asyncio
async def test_cache_set_stores_json_in_valkey():
    valkey = _FakeValkey()
    client = BifrostClient("http://bifrost", "", {"openai": "openai"}, valkey=valkey)
    await client._cache_set("my-key", [{"id": "m1"}], 60)
    assert valkey._store["my-key"] == json.dumps([{"id": "m1"}])
    assert valkey.set_calls[0][0] == "my-key"


@pytest.mark.asyncio
async def test_cache_set_swallows_valkey_error():
    client = BifrostClient(
        "http://bifrost", "", {"openai": "openai"}, valkey=_ErrorValkey()
    )
    # Must not raise
    await client._cache_set("some-key", [], 60)


@pytest.mark.asyncio
async def test_list_models_cache_hit_skips_bifrost():
    """Cache hit: Bifrost handler must never be called."""
    valkey = _FakeValkey()
    cache_key = "agent-orchestrator:model-cache:provider:openrouter"
    valkey._store[cache_key] = json.dumps(
        [{"id": "openrouter/cached-model", "name": None, "supported_methods": []}]
    )

    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": []}, request=request)

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 60.0
    try:
        models = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 0
    assert [m.id for m in models] == ["openrouter/cached-model"]


@pytest.mark.asyncio
async def test_list_models_cache_miss_fetches_from_bifrost_and_writes_to_valkey():
    valkey = _FakeValkey()
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"data": [{"id": "openrouter/live-model", "supported_methods": []}]},
            request=request,
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 60.0
    try:
        models = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 1
    assert [m.id for m in models] == ["openrouter/live-model"]

    cache_key = "agent-orchestrator:model-cache:provider:openrouter"
    assert cache_key in valkey._store
    stored = json.loads(valkey._store[cache_key])
    assert stored[0]["id"] == "openrouter/live-model"


@pytest.mark.asyncio
async def test_list_models_with_no_valkey_always_calls_bifrost():
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"data": [{"id": "openrouter/model-1", "supported_methods": []}]},
            request=request,
        )

    client = await _build_client(handler)  # valkey=None by default
    client._models_cache_ttl_seconds = 60.0
    try:
        await client.list_models("openrouter")
        await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 2


@pytest.mark.asyncio
async def test_list_models_with_zero_ttl_skips_valkey():
    valkey = _FakeValkey()
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"data": [{"id": "openrouter/model-1", "supported_methods": []}]},
            request=request,
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 0.0
    client._models_cache_ttl_int = 0
    client._unavailable_cache_ttl_int = 0
    try:
        await client.list_models("openrouter")
        await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 2
    assert valkey.get_calls == []
    assert valkey.set_calls == []


@pytest.mark.asyncio
async def test_list_models_valkey_error_falls_through_to_live_fetch():
    """Valkey always errors — must fall through to Bifrost without raising."""
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={"data": [{"id": "openrouter/live-model", "supported_methods": []}]},
            request=request,
        )

    client = await _build_client(handler, valkey=_ErrorValkey())
    client._models_cache_ttl_seconds = 60.0
    try:
        models = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert call_count == 1
    assert [m.id for m in models] == ["openrouter/live-model"]


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


# ---------------------------------------------------------------------------
# _fetch_all_models / get_model_context_length cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_all_models_cache_hit_skips_bifrost():
    """Cache hit: Bifrost handler must never be called for _fetch_all_models."""
    valkey = _FakeValkey()
    cache_key = "agent-orchestrator:model-cache:all"
    valkey._store[cache_key] = json.dumps(
        [
            {
                "id": "openai/gpt-4o",
                "name": "GPT-4o",
                "supported_methods": ["chat_completion"],
                "context_length": 128000,
            }
        ]
    )

    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": []}, request=request)

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 60.0
    client._models_cache_ttl_int = 60
    try:
        models = await client._fetch_all_models()
    finally:
        await client.aclose()

    assert call_count == 0
    assert len(models) == 1
    assert models[0].id == "openai/gpt-4o"
    assert models[0].context_length == 128000


@pytest.mark.asyncio
async def test_fetch_all_models_context_length_round_trips_through_cache():
    """context_length survives JSON serialisation in the cache write/read cycle."""
    valkey = _FakeValkey()
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "openai/gpt-4o",
                        "name": "GPT-4o",
                        "supported_methods": [],
                        "context_length": 128000,
                    }
                ]
            },
            request=request,
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 60.0
    client._models_cache_ttl_int = 60
    try:
        # First call — cache miss, writes to Valkey
        models_live = await client._fetch_all_models()
        assert call_count == 1
        assert models_live[0].context_length == 128000

        # Second call — cache hit, Bifrost not called again
        models_cached = await client._fetch_all_models()
    finally:
        await client.aclose()

    assert call_count == 1
    assert models_cached[0].context_length == 128000


@pytest.mark.asyncio
async def test_fetch_all_models_valkey_error_falls_through_to_live_fetch():
    """Valkey always errors — must fall through without raising."""
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "openai/gpt-4o",
                        "supported_methods": [],
                        "context_length": 64000,
                    }
                ]
            },
            request=request,
        )

    client = await _build_client(handler, valkey=_ErrorValkey())
    client._models_cache_ttl_seconds = 60.0
    client._models_cache_ttl_int = 60
    try:
        models = await client._fetch_all_models()
    finally:
        await client.aclose()

    assert call_count == 1
    assert models[0].context_length == 64000


# ---------------------------------------------------------------------------
# Negative cache tests (unavailable provider)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_models_caches_unavailable_provider():
    """A failing provider is negatively cached so the second call skips Bifrost."""
    valkey = _FakeValkey()
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            502, json={"error": {"message": "no api key"}}, request=request
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 60.0
    client._models_cache_ttl_int = 60
    client._unavailable_cache_ttl_int = 600
    try:
        with pytest.raises(BifrostError) as first:
            await client.list_models("openai")
        # Second call must fast-fail from the negative cache, not hit Bifrost.
        with pytest.raises(BifrostError) as second:
            await client.list_models("openai")
    finally:
        await client.aclose()

    assert call_count == 1
    assert first.value.code == "gateway_error"
    assert second.value.code == "gateway_error"
    assert "no api key" in str(second.value)
    unavailable_key = "agent-orchestrator:model-cache:unavailable:openai"
    assert unavailable_key in valkey._store


@pytest.mark.asyncio
async def test_list_models_retryable_failure_uses_short_negative_ttl():
    """A transient (retryable) failure is negatively cached with the short TTL
    so a recovered provider is not suppressed for the full unavailable TTL."""
    valkey = _FakeValkey()

    async def handler(request: httpx.Request) -> httpx.Response:
        # 503 -> retryable=True
        return httpx.Response(
            503, json={"error": {"message": "upstream"}}, request=request
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_int = 0
    client._unavailable_cache_ttl_int = 600
    client._unavailable_retryable_cache_ttl_int = 30
    try:
        with pytest.raises(BifrostError):
            await client.list_models("openai")
    finally:
        await client.aclose()

    unavailable_key = "agent-orchestrator:model-cache:unavailable:openai"
    setex = [call for call in valkey.setex_calls if call[0] == unavailable_key]
    assert len(setex) == 1
    assert setex[0][1] == 30  # short TTL, not the 600s definitive TTL


@pytest.mark.asyncio
async def test_list_models_non_retryable_failure_uses_full_negative_ttl():
    """A definitive (non-retryable) failure — e.g. a missing API key — keeps the
    full negative TTL so the slow HTTP call is not re-incurred."""
    valkey = _FakeValkey()

    async def handler(request: httpx.Request) -> httpx.Response:
        # 401 -> retryable=False
        return httpx.Response(
            401, json={"error": {"message": "no api key"}}, request=request
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_int = 0
    client._unavailable_cache_ttl_int = 600
    client._unavailable_retryable_cache_ttl_int = 30
    try:
        with pytest.raises(BifrostError):
            await client.list_models("openai")
    finally:
        await client.aclose()

    unavailable_key = "agent-orchestrator:model-cache:unavailable:openai"
    setex = [call for call in valkey.setex_calls if call[0] == unavailable_key]
    assert len(setex) == 1
    assert setex[0][1] == 600  # full definitive TTL


@pytest.mark.asyncio
async def test_list_models_negative_cache_disabled_when_ttl_zero():
    """With negative TTL 0, every failing call re-hits Bifrost (no negative cache)."""
    valkey = _FakeValkey()
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(502, json={"error": {"message": "down"}}, request=request)

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 0.0
    client._models_cache_ttl_int = 0
    client._unavailable_cache_ttl_int = 0
    try:
        with pytest.raises(BifrostError):
            await client.list_models("openai")
        with pytest.raises(BifrostError):
            await client.list_models("openai")
    finally:
        await client.aclose()

    assert call_count == 2
    assert "agent-orchestrator:model-cache:unavailable:openai" not in valkey._store


@pytest.mark.asyncio
async def test_list_models_negative_cache_short_circuits_without_http():
    """A pre-seeded negative marker fast-fails with zero Bifrost calls."""
    valkey = _FakeValkey()
    unavailable_key = "agent-orchestrator:model-cache:unavailable:openai"
    valkey._store[unavailable_key] = json.dumps(
        {"code": "timeout", "message": "timed out", "retryable": True}
    )
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"data": []}, request=request)

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 0.0
    client._models_cache_ttl_int = 0
    client._unavailable_cache_ttl_int = 600
    try:
        with pytest.raises(BifrostError) as exc_info:
            await client.list_models("openai")
    finally:
        await client.aclose()

    assert call_count == 0
    assert exc_info.value.code == "timeout"
    assert "timed out" in str(exc_info.value)


@pytest.mark.asyncio
async def test_list_models_success_clears_negative_marker():
    """A now-available provider is re-probed and its negative marker is cleared."""
    valkey = _FakeValkey()
    unavailable_key = "agent-orchestrator:model-cache:unavailable:openrouter"
    valkey._store[unavailable_key] = json.dumps(
        {"code": "timeout", "message": "timed out", "retryable": True}
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "openrouter/back-online", "supported_methods": []}]},
            request=request,
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 0.0
    client._models_cache_ttl_int = 0
    client._unavailable_cache_ttl_int = 600
    try:
        # Negative marker present -> fast-fail first.
        with pytest.raises(BifrostError):
            await client.list_models("openrouter")
        # Operator clears the cache (simulating /providers/refresh), then re-probe.
        await client.clear_model_cache(["openrouter"])
        models = await client.list_models("openrouter")
    finally:
        await client.aclose()

    assert [m.id for m in models] == ["openrouter/back-online"]
    assert unavailable_key not in valkey._store


@pytest.mark.asyncio
async def test_clear_model_cache_deletes_positive_negative_and_all_keys():
    valkey = _FakeValkey()
    valkey._store["agent-orchestrator:model-cache:provider:openai"] = "[]"
    valkey._store["agent-orchestrator:model-cache:unavailable:openai"] = "{}"
    valkey._store["agent-orchestrator:model-cache:all"] = "[]"

    client = BifrostClient("http://bifrost", "", {"openai": "openai"}, valkey=valkey)
    summary = await client.clear_model_cache(["openai"])

    assert summary == {"providers": 1, "keys_cleared": 3}
    assert "agent-orchestrator:model-cache:provider:openai" not in valkey._store
    assert "agent-orchestrator:model-cache:unavailable:openai" not in valkey._store
    assert "agent-orchestrator:model-cache:all" not in valkey._store


@pytest.mark.asyncio
async def test_get_model_context_length_uses_cache():
    """get_model_context_length hits Bifrost once and serves subsequent calls from cache."""
    valkey = _FakeValkey()
    call_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "gpt-4o-mini",
                        "supported_methods": [],
                        "context_length": 16000,
                    }
                ]
            },
            request=request,
        )

    client = await _build_client(handler, valkey=valkey)
    client._models_cache_ttl_seconds = 60.0
    client._models_cache_ttl_int = 60
    try:
        length1 = await client.get_model_context_length("openai", "gpt-4o-mini")
        length2 = await client.get_model_context_length("openai", "gpt-4o-mini")
    finally:
        await client.aclose()

    assert call_count == 1
    assert length1 == 16000
    assert length2 == 16000


# ---------------------------------------------------------------------------
# Stop reason capture
# ---------------------------------------------------------------------------


def _sse(*chunks: str) -> str:
    return "\n\n".join([*chunks, "data: [DONE]"])


@pytest.mark.asyncio
async def test_streaming_captures_the_finish_reason_from_the_final_chunk():
    """The chunk carrying it has an empty delta, so it used to contribute nothing."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse(
                'data: {"choices":[{"delta":{"content":"cut off"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
            ),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}, on_delta=lambda delta: None
        )
    finally:
        await client.aclose()

    assert response.finish_reason == "length"
    assert response.content == "cut off"


@pytest.mark.asyncio
async def test_streaming_reports_no_finish_reason_when_the_provider_sends_none():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse('data: {"choices":[{"delta":{"content":"hi"}}]}'),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}, on_delta=lambda delta: None
        )
    finally:
        await client.aclose()

    assert response.finish_reason is None


@pytest.mark.asyncio
async def test_streaming_keeps_the_last_non_null_finish_reason():
    """Some providers report per-choice reasons before the terminating chunk."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=_sse(
                'data: {"choices":[{"delta":{"content":"a"},"finish_reason":"stop"}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
            ),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}, on_delta=lambda delta: None
        )
    finally:
        await client.aclose()

    assert response.finish_reason == "length"


@pytest.mark.asyncio
async def test_non_streaming_captures_the_finish_reason_beside_the_message():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "done"}, "finish_reason": "stop"},
                ]
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}
        )
    finally:
        await client.aclose()

    assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_a_vendor_stop_reason_is_not_lost():
    """OpenRouter passes the upstream value through; Anthropic spells it differently."""

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "cut off"},
                        "native_finish_reason": "MAX_TOKENS",
                    },
                ]
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}
        )
    finally:
        await client.aclose()

    assert response.finish_reason == "MAX_TOKENS"


@pytest.mark.asyncio
async def test_an_anthropic_shaped_stop_reason_is_read():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "stop_reason": "max_tokens",
                "choices": [{"message": {"content": "cut off"}}],
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}
        )
    finally:
        await client.aclose()

    assert response.finish_reason == "max_tokens"


@pytest.mark.asyncio
async def test_a_normalised_finish_reason_wins_over_a_vendor_one():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": "done"},
                        "finish_reason": "length",
                        "native_finish_reason": "STOP",
                    },
                ]
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        response = await client.chat_completion(
            "openai", "gpt-4o-mini", [], None, {}, {}
        )
    finally:
        await client.aclose()

    assert response.finish_reason == "length"


@pytest.mark.asyncio
async def test_fetch_all_models_preserves_reasoning_capability_states():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://bifrost/v1/models")
        return httpx.Response(
            200,
            json={
                "data": [
                    {"id": "openrouter/no-metadata"},
                    {
                        "id": "openrouter/selected",
                        "reasoning": {"supported_efforts": ["minimal", "high"]},
                    },
                    {"id": "openrouter/no-reasoning", "reasoning": {"supported_efforts": []}},
                ]
            },
            request=request,
        )

    client = await _build_client(handler)
    try:
        models = await client._fetch_all_models()
    finally:
        await client.aclose()

    assert models[0].reasoning is None
    assert models[1].reasoning is not None
    assert models[1].reasoning.supported_efforts == ["minimal", "high"]
    assert models[2].reasoning is not None
    assert models[2].reasoning.supported_efforts == []


@pytest.mark.asyncio
async def test_cached_reasoning_capabilities_preserve_explicit_empty_list():
    valkey = _FakeValkey()

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "openrouter/no-reasoning", "reasoning": {"supported_efforts": []}}]},
            request=request,
        )

    client = await _build_client(handler, valkey=valkey)
    try:
        await client._fetch_all_models()
        cached = await client._fetch_all_models()
    finally:
        await client.aclose()

    assert cached[0].reasoning is not None
    assert cached[0].reasoning.supported_efforts == []
    assert len(valkey.setex_calls) == 1
