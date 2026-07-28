from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from dragncards_common.bifrost import (
    BifrostError,
    gateway_error,
    transport_error,
)
from dragncards_common.http_client import BaseAsyncClient

__all__ = ["BifrostError", "BifrostJudgeClient"]


class BifrostJudgeClient(BaseAsyncClient):
    """Bifrost gateway client for the isolated judge LLM.

    Every call is a FRESH, stateless chat completion under the dedicated judge
    identity. No session is reused: each invocation sends only the supplied
    messages.

    The judge identity is pinned by ``key_name``, sent as ``x-bf-api-key``:
    Bifrost resolves that header to the same-named key entry of whichever
    provider the model id routes to, which is what keeps judge traffic on a
    dedicated key for ANY provider. ``api_key`` is gateway auth only -- it does
    NOT select a provider key, so without ``key_name`` judge calls would draw
    the provider's normal (game-playing) weighted key pool.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_seconds: float = 120.0,
        key_name: str = "",
    ):
        super().__init__(base_url, timeout_seconds=timeout_seconds)
        self._api_key = api_key
        self._key_name = key_name.strip()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        if self._key_name:
            headers["x-bf-api-key"] = self._key_name
        return headers

    async def named_key_providers(self, key_name: str) -> frozenset[str] | None:
        """Providers that declare a key entry called ``key_name``.

        Reads Bifrost's key listing, which reports key NAMES, providers and
        masked/env-referenced values -- never a usable secret, and nothing from
        it is returned or logged here beyond provider names.

        Returns ``None`` when the listing cannot be read (admin auth enabled, an
        older gateway, Bifrost down): that is "unknown", not "missing". A listed
        entry whose ``env.`` reference is unset still appears here but is
        rejected at request time, so this is a check on the CONFIG entry, not on
        the secret being populated.
        """
        try:
            response = await self._http().get(f"{self._base_url}/api/keys")
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        try:
            entries = response.json()
        except ValueError:
            return None
        if not isinstance(entries, list):
            return None
        return frozenset(
            str(entry.get("provider", ""))
            for entry in entries
            if isinstance(entry, dict)
            and entry.get("name") == key_name
            and entry.get("provider")
        )

    @staticmethod
    def _build_payload(
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        gateway_options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        # gateway_options carries the reasoning mapping (mirrors the
        # agent-orchestrator's payload.update(gateway_options)).
        if gateway_options:
            payload.update(gateway_options)
        return payload

    async def judge(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        gateway_options: dict[str, Any] | None = None,
    ) -> str:
        """Run a fresh stateless judge completion and return the message content.

        ``model`` is the Bifrost ``provider/model`` id; its provider prefix picks
        the provider, and the ``x-bf-api-key`` header picks that provider's judge
        key, so the gateway attributes the traffic to the judge identity and
        budget, never a game-playing one. When the provider has no such key
        Bifrost fails the call with an explicit 400 rather than falling back.
        """
        payload = self._build_payload(model, messages, max_tokens, gateway_options)
        try:
            response = await self._http().post(
                f"{self._base_url}/openai/chat/completions",
                json=payload,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise transport_error(
                exc,
                timeout_message="Bifrost judge request timed out",
                network_message="Bifrost judge request failed",
            ) from exc

        if response.status_code >= 400:
            raise gateway_error(response)

        return self._extract_content(response.json())

    async def judge_stream(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        gateway_options: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a fresh judge completion as incremental text deltas.

        Yields content chunks as they arrive (OpenAI-style SSE chunks via the
        Bifrost gateway). The full text is the concatenation of all yields. The
        underlying httpx stream is cancellable: cancelling the awaiting task
        aborts the in-flight request promptly.
        """
        payload = self._build_payload(model, messages, max_tokens, gateway_options)
        payload["stream"] = True
        try:
            async with self._http().stream(
                "POST",
                f"{self._base_url}/openai/chat/completions",
                json=payload,
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise gateway_error(response)
                async for line in response.aiter_lines():
                    delta = self._parse_stream_line(line)
                    if delta:
                        yield delta
        except httpx.HTTPError as exc:
            raise transport_error(
                exc,
                timeout_message="Bifrost judge stream timed out",
                network_message="Bifrost judge stream failed",
            ) from exc

    @staticmethod
    def _flatten_content(content: Any, *, joiner: str) -> str:
        """Flatten an OpenAI ``content`` value to plain text.

        Accepts either a plain string or a list of typed content blocks (the
        ``{"type": "text", "text": ...}`` shape), returning the concatenation of
        the text blocks joined by ``joiner``. Any other shape yields ``""``.
        """
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return joiner.join(part for part in parts if part)
        return ""

    @classmethod
    def _parse_stream_line(cls, line: str) -> str:
        """Extract the incremental content from one OpenAI-style SSE data line."""
        line = line.strip()
        if not line.startswith("data:"):
            return ""
        data = line[len("data:") :].strip()
        if not data or data == "[DONE]":
            return ""
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            return ""
        try:
            delta = chunk["choices"][0].get("delta") or {}
        except KeyError, IndexError, TypeError:
            return ""
        return cls._flatten_content(delta.get("content"), joiner="")

    @classmethod
    def _extract_content(cls, data: dict[str, Any]) -> str:
        try:
            message = data["choices"][0]["message"]
        except KeyError, IndexError, TypeError:
            raise BifrostError(
                "invalid_response", "Bifrost returned an invalid judge response"
            )
        return cls._flatten_content(message.get("content"), joiner="\n")
