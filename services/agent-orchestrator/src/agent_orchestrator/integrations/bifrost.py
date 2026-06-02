from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Awaitable, Callable

import httpx

from agent_orchestrator.storage.valkey import RespConnection

logger = logging.getLogger(__name__)


class BifrostError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ReasoningDetail:
    index: int
    type: str | None = None
    text: str = ""
    signature: str | None = None


@dataclass(frozen=True)
class ChatDelta:
    content: str = ""
    reasoning: str = ""
    reasoning_details: list[ReasoningDetail] = field(default_factory=list)


@dataclass(frozen=True)
class ChatResponse:
    content: str
    tool_calls: list[ToolCall]
    raw: dict[str, Any]
    reasoning: str = ""
    reasoning_details: list[ReasoningDetail] = field(default_factory=list)


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str | None
    supported_methods: list[str]
    context_length: int | None = None


class BifrostClient:
    _CACHE_KEY_PREFIX = "agent-orchestrator:model-cache:"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        provider_prefixes: dict[str, str],
        *,
        models_cache_ttl_seconds: float = 60.0,
        valkey: RespConnection | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_prefixes = provider_prefixes
        self._models_cache_ttl_seconds = models_cache_ttl_seconds
        self._models_cache_ttl_int: int = round(models_cache_ttl_seconds)
        self._valkey = valkey
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def health(self) -> bool:
        try:
            response = await self._http_client.get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _cache_get(self, key: str) -> list[Any] | None:
        if self._valkey is None:
            return None
        try:
            raw = await self._valkey.execute("GET", key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            logger.warning("Valkey cache GET failed for key %r", key, exc_info=True)
            return None

    async def _cache_set(self, key: str, data: list[Any], ttl: int) -> None:
        if self._valkey is None:
            return
        try:
            await self._valkey.execute("SETEX", key, str(ttl), json.dumps(data))
        except Exception:
            logger.warning("Valkey cache SETEX failed for key %r", key, exc_info=True)

    @staticmethod
    def _model_info_from_dict(item: dict) -> ModelInfo:
        return ModelInfo(
            id=item["id"],
            name=item.get("name"),
            supported_methods=item.get("supported_methods") or [],
            context_length=item.get("context_length"),
        )

    async def list_models(self, provider_id: str) -> list[ModelInfo]:
        ttl = self._models_cache_ttl_int
        if ttl > 0:
            cache_key = f"{self._CACHE_KEY_PREFIX}provider:{provider_id}"
            cached = await self._cache_get(cache_key)
            if cached is not None:
                return [self._model_info_from_dict(item) for item in cached]

        headers = {"x-bf-list-models-provider": self._provider_prefixes[provider_id]}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._http_client.get(
                f"{self._base_url}/openai/v1/models",
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise BifrostError(
                "timeout", "Bifrost model listing timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise BifrostError(
                "network_error", "Bifrost model listing failed", retryable=True
            ) from exc

        if response.status_code >= 400:
            raise BifrostError(
                "gateway_error",
                self._extract_error_message(response),
                retryable=response.status_code >= 500 or response.status_code == 429,
            )

        payload = response.json()
        models = payload.get("data") or payload.get("models") or []
        result: list[ModelInfo] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not model_id:
                continue
            result.append(
                ModelInfo(
                    id=str(model_id),
                    name=item.get("name"),
                    supported_methods=list(item.get("supported_methods") or []),
                )
            )
        if ttl > 0:
            await self._cache_set(
                f"{self._CACHE_KEY_PREFIX}provider:{provider_id}",
                [
                    {
                        "id": m.id,
                        "name": m.name,
                        "supported_methods": m.supported_methods,
                    }
                    for m in result
                ],
                ttl,
            )
        return result

    async def _fetch_all_models(self) -> list[ModelInfo]:
        """Fetch the rich /v1/models listing (includes context_length per model)."""
        ttl = self._models_cache_ttl_int
        cache_key = f"{self._CACHE_KEY_PREFIX}all"
        if ttl > 0:
            cached = await self._cache_get(cache_key)
            if cached is not None:
                return [self._model_info_from_dict(item) for item in cached]

        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._http_client.get(
                f"{self._base_url}/v1/models",
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise BifrostError(
                "timeout", "Bifrost model listing timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise BifrostError(
                "network_error", "Bifrost model listing failed", retryable=True
            ) from exc

        if response.status_code >= 400:
            raise BifrostError(
                "gateway_error",
                self._extract_error_message(response),
                retryable=response.status_code >= 500 or response.status_code == 429,
            )

        payload = response.json()
        items = payload.get("data") or payload.get("models") or []
        result: list[ModelInfo] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            model_id = item.get("id")
            if not model_id:
                continue
            result.append(
                ModelInfo(
                    id=str(model_id),
                    name=item.get("name"),
                    supported_methods=list(item.get("supported_methods") or []),
                    context_length=item.get("context_length"),
                )
            )
        if ttl > 0:
            await self._cache_set(
                cache_key,
                [
                    {
                        "id": m.id,
                        "name": m.name,
                        "supported_methods": m.supported_methods,
                        "context_length": m.context_length,
                    }
                    for m in result
                ],
                ttl,
            )
        return result

    async def get_model_context_length(
        self, provider_id: str, model_name: str
    ) -> int | None:
        """Return context_length for the given model from /v1/models, or None if unknown."""
        resolved = self._resolve_model(provider_id, model_name)
        try:
            all_models = await self._fetch_all_models()
        except BifrostError:
            return None
        for m in all_models:
            if m.id == resolved:
                return m.context_length
        return None

    async def chat_completion(
        self,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        gateway_options: dict[str, Any],
        provider_options: dict[str, Any],
        on_delta: Callable[[ChatDelta], Awaitable[None]] | None = None,
    ) -> ChatResponse:
        payload: dict[str, Any] = {
            "model": self._resolve_model(provider_id, model_name),
            "messages": messages,
        }
        payload.update(gateway_options)
        payload.update(provider_options)
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if on_delta is not None:
            payload["stream"] = True
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if on_delta is None:
            response = await self._post_chat_completion(payload, headers)
            data = response.json()
            return self._parse_chat_response(data)

        return await self._stream_chat_completion(payload, headers, on_delta)

    def _resolve_model(self, provider_id: str, model_name: str) -> str:
        if "/" in model_name:
            return model_name
        provider_prefix = self._provider_prefixes[provider_id]
        if provider_prefix == "openai":
            return model_name
        return f"{provider_prefix}/{model_name}"

    def _normalize_content(self, content: Any) -> str:
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        return str(content)

    async def _post_chat_completion(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            response = await self._http_client.post(
                f"{self._base_url}/openai/chat/completions",
                json=payload,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise BifrostError(
                "timeout", "Bifrost request timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise BifrostError(
                "network_error", "Bifrost request failed", retryable=True
            ) from exc

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise BifrostError(
                "gateway_error",
                message,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        return response

    async def _stream_chat_completion(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
        on_delta: Callable[[ChatDelta], Awaitable[None]],
    ) -> ChatResponse:
        reasoning_buffers: dict[int, dict[str, Any]] = {}
        tool_call_buffers: dict[int, dict[str, Any]] = {}
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        raw_chunks: list[dict[str, Any]] = []

        try:
            async with self._http_client.stream(
                "POST",
                f"{self._base_url}/openai/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    message = self._extract_error_message(response)
                    raise BifrostError(
                        "gateway_error",
                        message,
                        retryable=response.status_code >= 500
                        or response.status_code == 429,
                    )

                async for raw_event in self._iter_sse_data(response):
                    if raw_event == "[DONE]":
                        break
                    chunk = json.loads(raw_event)
                    raw_chunks.append(chunk)
                    delta = self._extract_delta(chunk)
                    content = self._normalize_content(delta.get("content"))
                    reasoning = self._normalize_content(delta.get("reasoning"))
                    reasoning_details = self._parse_reasoning_details(
                        delta.get("reasoning_details") or []
                    )
                    tool_calls = delta.get("tool_calls") or []
                    if not reasoning and reasoning_details:
                        reasoning = "".join(
                            detail.text for detail in reasoning_details if detail.text
                        )

                    if content:
                        content_parts.append(content)
                    if reasoning:
                        reasoning_parts.append(reasoning)
                    if reasoning_details:
                        self._merge_reasoning_details(
                            reasoning_buffers, reasoning_details
                        )
                    if tool_calls:
                        self._merge_tool_call_deltas(tool_call_buffers, tool_calls)

                    if content or reasoning or reasoning_details:
                        callback_result = on_delta(
                            ChatDelta(
                                content=content,
                                reasoning=reasoning,
                                reasoning_details=reasoning_details,
                            )
                        )
                        if isawaitable(callback_result):
                            await callback_result
        except json.JSONDecodeError as exc:
            raise BifrostError(
                "invalid_response", "Bifrost returned an invalid streamed response"
            ) from exc
        except httpx.TimeoutException as exc:
            raise BifrostError(
                "timeout", "Bifrost request timed out", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise BifrostError(
                "network_error", "Bifrost request failed", retryable=True
            ) from exc

        return ChatResponse(
            content="".join(content_parts),
            tool_calls=self._finalize_streamed_tool_calls(tool_call_buffers),
            raw={"chunks": raw_chunks},
            reasoning="".join(reasoning_parts),
            reasoning_details=self._finalize_reasoning_details(reasoning_buffers),
        )

    def _parse_chat_response(self, data: dict[str, Any]) -> ChatResponse:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BifrostError(
                "invalid_response", "Bifrost returned an invalid response"
            ) from exc

        reasoning_details = self._parse_reasoning_details(
            message.get("reasoning_details") or []
        )
        reasoning = self._normalize_content(message.get("reasoning"))
        if not reasoning and reasoning_details:
            reasoning = "".join(
                detail.text for detail in reasoning_details if detail.text
            )
        return ChatResponse(
            content=self._normalize_content(message.get("content")),
            tool_calls=self._parse_tool_calls(message.get("tool_calls") or []),
            raw=data,
            reasoning=reasoning,
            reasoning_details=reasoning_details,
        )

    def _parse_tool_calls(self, payload: list[Any]) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for tool_call in payload:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {"raw": raw_arguments}
            tool_calls.append(
                ToolCall(
                    id=str(tool_call.get("id", "tool-call")),
                    name=str(function.get("name", "unknown_tool")),
                    arguments=arguments,
                )
            )
        return tool_calls

    def _parse_reasoning_details(self, payload: list[Any]) -> list[ReasoningDetail]:
        details: list[ReasoningDetail] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            details.append(
                ReasoningDetail(
                    index=int(item.get("index", len(details))),
                    type=None if item.get("type") is None else str(item.get("type")),
                    text=self._normalize_content(item.get("text")),
                    signature=(
                        None
                        if item.get("signature") is None
                        else str(item.get("signature"))
                    ),
                )
            )
        return details

    def _extract_delta(self, chunk: dict[str, Any]) -> dict[str, Any]:
        try:
            choices = chunk["choices"]
            if not choices:
                return {}
            return choices[0].get("delta") or {}
        except KeyError, IndexError, TypeError:
            return {}

    async def _iter_sse_data(self, response: httpx.Response):
        data_lines: list[str] = []
        async for line in response.aiter_lines():
            if not line:
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines.clear()
                continue
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            yield "\n".join(data_lines)

    def _merge_reasoning_details(
        self,
        buffers: dict[int, dict[str, Any]],
        details: list[ReasoningDetail],
    ) -> None:
        for detail in details:
            buffer = buffers.setdefault(
                detail.index,
                {
                    "index": detail.index,
                    "type": detail.type,
                    "text_parts": [],
                    "signature": None,
                },
            )
            if detail.type is not None:
                buffer["type"] = detail.type
            if detail.text:
                buffer["text_parts"].append(detail.text)
            if detail.signature is not None:
                buffer["signature"] = detail.signature

    def _finalize_reasoning_details(
        self, buffers: dict[int, dict[str, Any]]
    ) -> list[ReasoningDetail]:
        return [
            ReasoningDetail(
                index=index,
                type=buffer["type"],
                text="".join(buffer["text_parts"]),
                signature=buffer["signature"],
            )
            for index, buffer in sorted(buffers.items())
        ]

    def _merge_tool_call_deltas(
        self,
        buffers: dict[int, dict[str, Any]],
        payload: list[Any],
    ) -> None:
        for item in payload:
            if not isinstance(item, dict):
                continue
            index = int(item.get("index", len(buffers)))
            buffer = buffers.setdefault(
                index, {"id": "tool-call", "name": "", "arguments_parts": []}
            )
            if item.get("id") is not None:
                buffer["id"] = str(item["id"])
            function = item.get("function") or {}
            if function.get("name") is not None:
                buffer["name"] += str(function["name"])
            if function.get("arguments") is not None:
                buffer["arguments_parts"].append(str(function["arguments"]))

    def _finalize_streamed_tool_calls(
        self, buffers: dict[int, dict[str, Any]]
    ) -> list[ToolCall]:
        tool_calls: list[ToolCall] = []
        for _, buffer in sorted(buffers.items()):
            raw_arguments = "".join(buffer["arguments_parts"]) or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {"raw": raw_arguments}
            tool_calls.append(
                ToolCall(
                    id=buffer["id"],
                    name=buffer["name"] or "unknown_tool",
                    arguments=arguments,
                )
            )
        return tool_calls

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"Bifrost returned HTTP {response.status_code}"
        detail = payload.get("error") or payload.get("message") or payload
        if isinstance(detail, dict):
            detail = (
                detail.get("message")
                or detail.get("detail")
                or "Bifrost request failed"
            )
        return str(detail)
