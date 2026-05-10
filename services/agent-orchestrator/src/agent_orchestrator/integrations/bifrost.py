from __future__ import annotations

import json
from dataclasses import dataclass
from time import monotonic
from typing import Any

import httpx


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
class ChatResponse:
    content: str
    tool_calls: list[ToolCall]
    raw: dict[str, Any]


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str | None
    supported_methods: list[str]


@dataclass(frozen=True)
class CachedModelListing:
    expires_at: float
    models: list[ModelInfo]


class BifrostClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        provider_prefixes: dict[str, str],
        *,
        models_cache_ttl_seconds: float = 60.0,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_prefixes = provider_prefixes
        self._models_cache_ttl_seconds = models_cache_ttl_seconds
        self._models_cache: dict[str, CachedModelListing] = {}
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def health(self) -> bool:
        try:
            response = await self._http_client.get(f"{self._base_url}/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def list_models(self, provider_id: str) -> list[ModelInfo]:
        cached = self._models_cache.get(provider_id)
        if cached is not None and cached.expires_at > monotonic():
            return cached.models

        headers = {"x-bf-list-models-provider": self._provider_prefixes[provider_id]}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._http_client.get(
                f"{self._base_url}/openai/v1/models",
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise BifrostError("timeout", "Bifrost model listing timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise BifrostError("network_error", "Bifrost model listing failed", retryable=True) from exc

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
        if self._models_cache_ttl_seconds > 0:
            self._models_cache[provider_id] = CachedModelListing(
                expires_at=monotonic() + self._models_cache_ttl_seconds,
                models=result,
            )
        return result

    async def chat_completion(
        self,
        provider_id: str,
        model_name: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        gateway_options: dict[str, Any],
        provider_options: dict[str, Any],
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
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._http_client.post(
                f"{self._base_url}/openai/chat/completions",
                json=payload,
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise BifrostError("timeout", "Bifrost request timed out", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise BifrostError("network_error", "Bifrost request failed", retryable=True) from exc

        if response.status_code >= 400:
            message = self._extract_error_message(response)
            raise BifrostError(
                "gateway_error",
                message,
                retryable=response.status_code >= 500 or response.status_code == 429,
            )

        data = response.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BifrostError("invalid_response", "Bifrost returned an invalid response") from exc

        tool_calls: list[ToolCall] = []
        for tool_call in message.get("tool_calls") or []:
            raw_arguments = tool_call.get("function", {}).get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {"raw": raw_arguments}
            tool_calls.append(
                ToolCall(
                    id=tool_call.get("id", "tool-call"),
                    name=tool_call.get("function", {}).get("name", "unknown_tool"),
                    arguments=arguments,
                )
            )
        return ChatResponse(
            content=self._normalize_content(message.get("content")),
            tool_calls=tool_calls,
            raw=data,
        )

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

    def _extract_error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return f"Bifrost returned HTTP {response.status_code}"
        detail = payload.get("error") or payload.get("message") or payload
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("detail") or "Bifrost request failed"
        return str(detail)
