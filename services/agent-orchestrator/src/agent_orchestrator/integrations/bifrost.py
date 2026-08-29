from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from inspect import isawaitable
from typing import Any, Awaitable, Callable

import httpx
from dragncards_common.bifrost import (
    BifrostError,
    extract_error_message,
    gateway_error,
    transport_error,
)

from agent_orchestrator.storage.valkey import RespConnection

logger = logging.getLogger(__name__)


def _brief(exc: BaseException) -> str:
    """Render an exception as one short line for a recoverable-failure log.

    The model cache is an optimisation: every reader falls back to a live Bifrost
    fetch when it misses, so a transport error here costs latency and nothing else.
    It was logged with a full stack trace, which made an entirely handled condition
    look like a crash and helped drown the log when Valkey churned (DRA-35). The
    type and message identify the fault; the traceback added nothing, because the
    only call that can throw is the line above the log.
    """
    return f"{type(exc).__name__}: {exc}"


def _ttl_int(seconds: float) -> int:
    """Round a TTL to whole seconds for SETEX.

    A configured positive TTL never collapses to ``0`` (which would silently
    disable that cache tier); only a non-positive value disables it.
    """
    if seconds <= 0:
        return 0
    return max(1, round(seconds))


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
    # Why the model stopped, as the provider reported it. `raw` has two shapes —
    # a list of streamed chunks, or the whole response document — so a caller
    # that dug this out itself would end up handling only one of them, which is
    # how `extract_tokens_from_response` came to read only the non-streamed one.
    # Normalising here keeps every consumer shape-blind. `None` means the
    # provider said nothing, which is never treated as evidence of anything.
    finish_reason: str | None = None


def _stop_reason_from_choice(choice: Any) -> str | None:
    """Read why the model stopped out of one choice, whatever dialect it speaks.

    Priority matters. `finish_reason` is the OpenAI-compatible field and the one
    Bifrost's `/openai/chat/completions` endpoint emits, so a normalised value
    always wins. `native_finish_reason` is OpenRouter's passthrough of the
    upstream provider's own spelling of the same thing, and OpenRouter is a
    configured provider here. `stop_reason` is the Anthropic spelling, which a
    gateway proxying an Anthropic response without full normalisation leaks.
    """
    if not isinstance(choice, dict):
        return None
    message = choice.get("message")
    candidates = [
        choice.get("finish_reason"),
        choice.get("native_finish_reason"),
        choice.get("stop_reason"),
        message.get("stop_reason") if isinstance(message, dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate
    return None


@dataclass(frozen=True)
class ModelReasoning:
    """Optional reasoning capabilities reported by Bifrost for one model."""

    mandatory: bool | None = None
    default_enabled: bool | None = None
    supported_efforts: list[str] | None = None
    default_effort: str | None = None

    @classmethod
    def from_dict(cls, item: dict[str, Any]) -> "ModelReasoning":
        raw_efforts = item.get("supported_efforts")
        supported_efforts = (
            [str(effort) for effort in raw_efforts]
            if isinstance(raw_efforts, list)
            else None
        )
        return cls(
            mandatory=(
                item.get("mandatory")
                if isinstance(item.get("mandatory"), bool)
                else None
            ),
            default_enabled=(
                item.get("default_enabled")
                if isinstance(item.get("default_enabled"), bool)
                else None
            ),
            supported_efforts=supported_efforts,
            default_effort=(
                str(item["default_effort"])
                if item.get("default_effort") is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.mandatory is not None:
            result["mandatory"] = self.mandatory
        if self.default_enabled is not None:
            result["default_enabled"] = self.default_enabled
        if self.supported_efforts is not None:
            result["supported_efforts"] = list(self.supported_efforts)
        if self.default_effort is not None:
            result["default_effort"] = self.default_effort
        return result


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str | None
    supported_methods: list[str]
    context_length: int | None = None
    reasoning: ModelReasoning | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "supported_methods": list(self.supported_methods),
        }
        if self.context_length is not None:
            result["context_length"] = self.context_length
        if self.reasoning is not None:
            result["reasoning"] = self.reasoning.to_dict()
        return result


class BifrostClient:
    _CACHE_KEY_PREFIX = "agent-orchestrator:model-cache:"
    _ALL_CACHE_KEY = f"{_CACHE_KEY_PREFIX}all"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        provider_prefixes: dict[str, str],
        *,
        models_cache_ttl_seconds: float = 60.0,
        list_models_timeout_seconds: float = 8.0,
        unavailable_cache_ttl_seconds: float = 600.0,
        unavailable_retryable_cache_ttl_seconds: float = 30.0,
        valkey: RespConnection | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_prefixes = provider_prefixes
        self._models_cache_ttl_seconds = models_cache_ttl_seconds
        self._models_cache_ttl_int: int = _ttl_int(models_cache_ttl_seconds)
        self._list_models_timeout_seconds = list_models_timeout_seconds
        self._unavailable_cache_ttl_seconds = unavailable_cache_ttl_seconds
        self._unavailable_cache_ttl_int: int = _ttl_int(unavailable_cache_ttl_seconds)
        self._unavailable_retryable_cache_ttl_int: int = _ttl_int(
            unavailable_retryable_cache_ttl_seconds
        )
        self._valkey = valkey
        self._http_client = httpx.AsyncClient(timeout=60.0)

    def _provider_cache_key(self, provider_id: str) -> str:
        return f"{self._CACHE_KEY_PREFIX}provider:{provider_id}"

    def _provider_unavailable_key(self, provider_id: str) -> str:
        return f"{self._CACHE_KEY_PREFIX}unavailable:{provider_id}"

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
        except Exception as exc:
            logger.warning(
                "Valkey cache GET failed for key %r (%s); serving live",
                key,
                _brief(exc),
            )
            return None

    async def _cache_set(
        self, key: str, data: list[Any] | dict[str, Any], ttl: int
    ) -> None:
        if self._valkey is None:
            return
        try:
            await self._valkey.execute("SETEX", key, str(ttl), json.dumps(data))
        except Exception as exc:
            logger.warning(
                "Valkey cache SETEX failed for key %r (%s); not cached",
                key,
                _brief(exc),
            )

    async def _cache_get_unavailable(self, key: str) -> dict[str, Any] | None:
        if self._valkey is None:
            return None
        try:
            raw = await self._valkey.execute("GET", key)
            if raw is None:
                return None
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except Exception as exc:
            logger.warning(
                "Valkey cache GET failed for key %r (%s); serving live",
                key,
                _brief(exc),
            )
            return None

    async def _cache_del(self, *keys: str) -> None:
        if self._valkey is None or not keys:
            return
        try:
            await self._valkey.execute("DEL", *keys)
        except Exception as exc:
            logger.warning(
                "Valkey cache DEL failed for keys %r (%s)", keys, _brief(exc)
            )

    async def clear_model_cache(self, provider_ids: list[str]) -> dict[str, int]:
        """Flush positive and negative model-cache entries.

        Deletes the per-provider positive cache, the per-provider negative
        (``unavailable``) marker for each given provider id, and the shared
        ``:all`` listing. Returns a small summary so callers can report how many
        keys were targeted. Safe to call when Valkey is unavailable.
        """
        keys: list[str] = [self._ALL_CACHE_KEY]
        for provider_id in provider_ids:
            keys.append(self._provider_cache_key(provider_id))
            keys.append(self._provider_unavailable_key(provider_id))
        await self._cache_del(*keys)
        return {"providers": len(provider_ids), "keys_cleared": len(keys)}

    @staticmethod
    def _model_to_dict(model: ModelInfo) -> dict[str, object]:
        serializer = getattr(model, "to_dict", None)
        if callable(serializer):
            return serializer()
        result: dict[str, object] = {
            "id": model.id,
            "name": getattr(model, "name", None),
            "supported_methods": getattr(model, "supported_methods", []),
        }
        context_length = getattr(model, "context_length", None)
        if context_length is not None:
            result["context_length"] = context_length
        return result

    @staticmethod
    def _model_info_from_dict(item: dict) -> ModelInfo:
        reasoning = item.get("reasoning")
        return ModelInfo(
            id=item["id"],
            name=item.get("name"),
            supported_methods=item.get("supported_methods") or [],
            context_length=item.get("context_length"),
            reasoning=(
                ModelReasoning.from_dict(reasoning)
                if isinstance(reasoning, dict)
                else None
            ),
        )

    async def list_models(self, provider_id: str) -> list[ModelInfo]:
        ttl = self._models_cache_ttl_int
        provider_cache_key = self._provider_cache_key(provider_id)
        unavailable_key = self._provider_unavailable_key(provider_id)
        negative_ttl = self._unavailable_cache_ttl_int
        if ttl > 0:
            cached = await self._cache_get(provider_cache_key)
            if cached is not None:
                return [self._model_info_from_dict(item) for item in cached]
        # Negative cache: a recently-failed provider fast-fails without the slow
        # HTTP call, but the marker expires so an added API key is re-probed.
        if negative_ttl > 0:
            marker = await self._cache_get_unavailable(unavailable_key)
            if marker is not None:
                raise BifrostError(
                    str(marker.get("code") or "gateway_error"),
                    str(marker.get("message") or "Provider unavailable"),
                    retryable=bool(marker.get("retryable", True)),
                )

        try:
            result = await self._list_models_uncached(provider_id)
        except BifrostError as exc:
            # A transient (retryable) failure — timeout, network blip, 5xx, or
            # 429 — must not suppress the provider for the full negative TTL:
            # once it recovers, every list_models call would keep fast-failing
            # from the stale marker for up to 10 minutes. Retryable failures use
            # a much shorter TTL so a brief outage is re-probed quickly, while
            # definitive (non-retryable) failures — e.g. a missing API key —
            # keep the long TTL so we do not re-incur the slow HTTP call.
            if negative_ttl > 0:
                write_ttl = (
                    self._unavailable_retryable_cache_ttl_int
                    if exc.retryable
                    else negative_ttl
                )
                if write_ttl > 0:
                    await self._cache_set(
                        unavailable_key,
                        {
                            "code": exc.code,
                            "message": str(exc),
                            "retryable": exc.retryable,
                        },
                        write_ttl,
                    )
            raise

        if ttl > 0:
            await self._cache_set(
                provider_cache_key,
                [self._model_to_dict(m) for m in result],
                ttl,
            )
        # A successful listing clears any stale negative marker so the provider
        # is no longer reported unavailable before its negative TTL elapses.
        if negative_ttl > 0:
            await self._cache_del(unavailable_key)
        return result

    def _model_lookup_ids(self, provider_id: str, model_id: str) -> tuple[str, ...]:
        prefix = self._provider_prefixes[provider_id]
        qualified = (
            model_id if model_id.startswith(f"{prefix}/") else f"{prefix}/{model_id}"
        )
        bare = (
            model_id[len(prefix) + 1 :]
            if model_id.startswith(f"{prefix}/")
            else model_id
        )
        # Prefer the selected provider's qualified id. Bare aliases are only a
        # compatibility fallback and may collide across providers.
        return tuple(dict.fromkeys((qualified, model_id, bare)))

    async def _enrich_model_infos(
        self, provider_id: str, models: list[ModelInfo]
    ) -> list[ModelInfo]:
        try:
            rich_models = await self._fetch_all_models()
        except Exception as exc:
            # The compatibility listing remains useful when rich metadata is
            # unavailable, so model discovery never depends on this enrichment.
            logger.info(
                "Could not enrich model capabilities from Bifrost (%s)", _brief(exc)
            )
            return models

        by_id: dict[str, ModelInfo] = {}
        for model in rich_models:
            for candidate in self._model_lookup_ids(provider_id, model.id):
                by_id.setdefault(candidate, model)

        enriched: list[ModelInfo] = []
        for model in models:
            rich = next(
                (
                    by_id[candidate]
                    for candidate in self._model_lookup_ids(provider_id, model.id)
                    if candidate in by_id
                ),
                None,
            )
            if rich is None:
                enriched.append(model)
                continue
            enriched.append(
                ModelInfo(
                    id=model.id,
                    name=model.name or rich.name,
                    supported_methods=model.supported_methods or rich.supported_methods,
                    context_length=model.context_length or rich.context_length,
                    reasoning=rich.reasoning,
                )
            )
        return enriched

    async def list_models_with_capabilities(self, provider_id: str) -> list[ModelInfo]:
        """List provider models with best-effort rich reasoning metadata."""
        models = await self.list_models(provider_id)
        enriched = await self._enrich_model_infos(provider_id, models)
        ttl = getattr(self, "_models_cache_ttl_int", 0)
        if ttl > 0:
            await self._cache_set(
                self._provider_cache_key(provider_id),
                [self._model_to_dict(model) for model in enriched],
                ttl,
            )
        return enriched

    async def get_model_reasoning(
        self, provider_id: str, model_name: str
    ) -> ModelReasoning | None:
        """Return rich reasoning metadata, or ``None`` when it is unavailable."""
        try:
            rich_models = await self._fetch_all_models()
        except Exception:
            return None
        by_id: dict[str, ModelInfo] = {}
        for model in rich_models:
            for candidate in self._model_lookup_ids(provider_id, model.id):
                by_id.setdefault(candidate, model)
        model = next(
            (
                by_id[candidate]
                for candidate in self._model_lookup_ids(provider_id, model_name)
                if candidate in by_id
            ),
            None,
        )
        return model.reasoning if model is not None else None

    async def _list_models_uncached(self, provider_id: str) -> list[ModelInfo]:
        headers = {"x-bf-list-models-provider": self._provider_prefixes[provider_id]}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._http_client.get(
                f"{self._base_url}/openai/v1/models",
                headers=headers,
                timeout=self._list_models_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise transport_error(
                exc,
                timeout_message="Bifrost model listing timed out",
                network_message="Bifrost model listing failed",
            ) from exc

        if response.status_code >= 400:
            raise gateway_error(response)

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
                    reasoning=(
                        ModelReasoning.from_dict(item["reasoning"])
                        if isinstance(item.get("reasoning"), dict)
                        else None
                    ),
                )
            )
        return result

    async def _fetch_all_models(self) -> list[ModelInfo]:
        """Fetch the rich /v1/models listing (includes context_length per model)."""
        ttl = self._models_cache_ttl_int
        cache_key = self._ALL_CACHE_KEY
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
                timeout=self._list_models_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise transport_error(
                exc,
                timeout_message="Bifrost model listing timed out",
                network_message="Bifrost model listing failed",
            ) from exc

        if response.status_code >= 400:
            raise gateway_error(response)

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
                    reasoning=(
                        ModelReasoning.from_dict(item["reasoning"])
                        if isinstance(item.get("reasoning"), dict)
                        else None
                    ),
                )
            )
        if ttl > 0:
            await self._cache_set(
                cache_key,
                [m.to_dict() for m in result],
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
        reserved = {"model", "messages", "tools", "tool_choice", "stream"}
        payload.update(
            {
                key: value
                for key, value in gateway_options.items()
                if key not in reserved
            }
        )
        payload.update(
            {
                key: value
                for key, value in provider_options.items()
                if key not in reserved
            }
        )
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
        except httpx.HTTPError as exc:
            raise transport_error(
                exc,
                timeout_message="Bifrost request timed out",
                network_message="Bifrost request failed",
            ) from exc

        if response.status_code >= 400:
            raise gateway_error(response)
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
        finish_reason: str | None = None

        try:
            async with self._http_client.stream(
                "POST",
                f"{self._base_url}/openai/chat/completions",
                json=payload,
                headers=headers,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise gateway_error(response)

                async for raw_event in self._iter_sse_data(response):
                    if raw_event == "[DONE]":
                        break
                    chunk = json.loads(raw_event)
                    raw_chunks.append(chunk)
                    # The chunk that carries the stop reason has an empty delta,
                    # so it would otherwise contribute nothing. Last non-null
                    # wins: providers differ over whether they send it on the
                    # final chunk or alongside the last content.
                    chunk_choices = (
                        chunk.get("choices") or [] if isinstance(chunk, dict) else []
                    )
                    if chunk_choices:
                        chunk_finish_reason = _stop_reason_from_choice(chunk_choices[0])
                        if chunk_finish_reason is not None:
                            finish_reason = chunk_finish_reason
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
        except httpx.HTTPError as exc:
            raise transport_error(
                exc,
                timeout_message="Bifrost request timed out",
                network_message="Bifrost request failed",
            ) from exc

        return ChatResponse(
            content="".join(content_parts),
            tool_calls=self._finalize_streamed_tool_calls(tool_call_buffers),
            raw={"chunks": raw_chunks},
            reasoning="".join(reasoning_parts),
            reasoning_details=self._finalize_reasoning_details(reasoning_buffers),
            finish_reason=finish_reason,
        )

    def _parse_chat_response(self, data: dict[str, Any]) -> ChatResponse:
        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise BifrostError(
                "invalid_response", "Bifrost returned an invalid response"
            ) from exc

        # `finish_reason` is a sibling of `message` inside the same choice, so
        # reading only `message` — as this parser used to — discards it. A
        # top-level `stop_reason` is the Anthropic document shape leaking whole.
        finish_reason = _stop_reason_from_choice(choice)
        if finish_reason is None:
            top_level = data.get("stop_reason")
            if isinstance(top_level, str) and top_level.strip():
                finish_reason = top_level

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
            finish_reason=finish_reason,
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
        return extract_error_message(response)
