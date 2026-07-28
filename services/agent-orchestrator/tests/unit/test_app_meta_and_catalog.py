from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_orchestrator.integrations.bifrost import BifrostClient, BifrostError

from .app_test_support import (
    UNIT_ENABLED_PROVIDER_IDS,
    FakeBifrostClient,
    build_test_app,
)


def test_health(app):
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_dependencies(app):
    with TestClient(app) as client:
        response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "database": True,
        "bifrost": True,
        "valkey": True,
        "worker": True,
    }


def test_list_providers(app):
    expected_provider_ids = set(app.state.settings.enabled_provider_ids)
    with TestClient(app) as client:
        response = client.get("/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    provider_ids = {item["provider_id"] for item in providers}
    assert provider_ids == expected_provider_ids
    for provider in providers:
        assert provider["available"] is True
        assert provider["error"] is None
        # The fake Bifrost client only reports unprefixed models, which are
        # filtered out for prefixed providers, so every enabled provider lists
        # no models.
        assert provider["models"] == []


@pytest.mark.asyncio
async def test_unit_app_pins_provider_set_regardless_of_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The unit harness must not inherit ENABLED_PROVIDER_IDS.

    Guards the regression where a developer narrowing their `.env` to the
    providers they hold keys for (for example dropping OpenAI) silently changed
    which providers the unit suite exercised.
    """
    monkeypatch.setenv("ENABLED_PROVIDER_IDS", "mistral")
    app, engine = await build_test_app(tmp_path)
    try:
        assert app.state.settings.enabled_provider_ids == tuple(
            UNIT_ENABLED_PROVIDER_IDS.split(",")
        )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_providers_filters_models_to_requested_provider(tmp_path: Path):
    class MixedModelBifrostClient(FakeBifrostClient):
        async def list_models(self, provider_id: str):
            if provider_id == "openai":
                model_ids = [
                    "gpt-4o-mini",
                    "openai/gpt-4.1-mini",
                    "openrouter/google/gemini-2.5-pro",
                ]
            else:
                model_ids = [
                    "gemini/gemini-2.0-flash",
                    "openrouter/openai/gpt-4o-mini",
                    "gpt-4o-mini",
                ]
            return [
                type(
                    "ModelInfo",
                    (),
                    {
                        "id": model_id,
                        "name": model_id,
                        "supported_methods": ["chat_completion"],
                    },
                )()
                for model_id in model_ids
            ]

    app, engine = await build_test_app(
        tmp_path, bifrost_client=MixedModelBifrostClient()
    )
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        assert providers["openai"]["models"] == ["openai/gpt-4.1-mini"]
        assert providers["gemini"]["models"] == ["gemini/gemini-2.0-flash"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_providers_marks_unavailable_provider(tmp_path: Path):
    app, engine = await build_test_app(tmp_path, unavailable_provider_ids={"gemini"})
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        assert providers["openai"]["available"] is True
        assert providers["openai"]["error"] is None
        assert providers["gemini"]["available"] is False
        assert providers["gemini"]["models"] == []
        assert "unavailable" in providers["gemini"]["error"].lower()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_providers_isolates_failing_provider(tmp_path: Path):
    """One provider raising must not stop working providers from returning models."""

    class OneBrokenProviderClient(FakeBifrostClient):
        async def list_models(self, provider_id: str):
            if provider_id == "gemini":
                raise BifrostError(
                    "timeout", "Bifrost model listing timed out", retryable=True
                )
            return await super().list_models(provider_id)

    app, engine = await build_test_app(
        tmp_path, bifrost_client=OneBrokenProviderClient()
    )
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        # Working provider still responds successfully despite the broken one.
        assert providers["openai"]["available"] is True
        assert providers["openai"]["error"] is None
        # Broken provider is flagged unavailable with a clear error.
        assert providers["gemini"]["available"] is False
        assert providers["gemini"]["models"] == []
        assert "timed out" in providers["gemini"]["error"].lower()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_providers_does_not_wait_for_hanging_provider(tmp_path: Path):
    """A provider that hangs must be bounded by the configured timeout, not 60s."""

    class HangingProviderClient(FakeBifrostClient):
        async def list_models(self, provider_id: str):
            if provider_id == "gemini":
                # Simulate a keyless/broken provider that never responds.
                await asyncio.sleep(60.0)
            return await super().list_models(provider_id)

    # Short timeout so the catalog guard fires quickly. Guard margin adds 2s on
    # top, so the endpoint must return in well under the 60s sleep above.
    app, engine = await build_test_app(
        tmp_path,
        bifrost_client=HangingProviderClient(),
        list_models_timeout_seconds=0.1,
    )
    try:
        with TestClient(app) as client:
            start = time.monotonic()
            response = client.get("/providers")
            elapsed = time.monotonic() - start
        assert response.status_code == 200
        # Must return promptly, far below the 60s upstream sleep.
        assert elapsed < 10.0
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        assert providers["openai"]["available"] is True
        assert providers["gemini"]["available"] is False
        assert providers["gemini"]["models"] == []
        assert "timed out" in providers["gemini"]["error"].lower()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_providers_keeps_unprefixed_lmstudio_models(tmp_path: Path):
    class LocalModelBifrostClient(FakeBifrostClient):
        async def list_models(self, provider_id: str):
            if provider_id != "lmstudio":
                return await super().list_models(provider_id)
            model_ids = [
                "qwen3.5-0.8b",
                "lmstudio/backup-local-model",
                "openrouter/google/gemini-2.5-pro",
            ]
            return [
                type(
                    "ModelInfo",
                    (),
                    {
                        "id": model_id,
                        "name": model_id,
                        "supported_methods": ["chat_completion"],
                    },
                )()
                for model_id in model_ids
            ]

    app, engine = await build_test_app(
        tmp_path,
        bifrost_client=LocalModelBifrostClient(),
        enabled_provider_ids="lmstudio",
    )
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = response.json()["providers"]
        assert providers == [
            {
                "provider_id": "lmstudio",
                "model_prefix": "lmstudio",
                "models": ["lmstudio/backup-local-model"],
                "available": True,
                "error": None,
            }
        ]
    finally:
        await engine.dispose()


class _CountingValkey:
    """In-process Valkey stand-in supporting GET/SETEX/DEL for endpoint tests."""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def execute(self, *parts: object):
        command = str(parts[0]).upper()
        if command == "GET":
            return self._store.get(str(parts[1]))
        if command == "SETEX":
            self._store[str(parts[1])] = str(parts[3])
            return "OK"
        if command == "DEL":
            removed = 0
            for key in parts[1:]:
                if self._store.pop(str(key), None) is not None:
                    removed += 1
            return removed
        raise RuntimeError(f"unsupported command {command!r}")


class _NegativeCacheBifrostClient(BifrostClient):
    """Real BifrostClient caching path with a stubbed underlying fetch.

    Drives the genuine positive/negative Valkey cache logic in `list_models`
    while letting tests toggle availability and count underlying probes.
    """

    def __init__(self, *, available: bool):
        super().__init__(
            "http://bifrost",
            "",
            {"openai": "openai", "gemini": "gemini"},
            models_cache_ttl_seconds=600.0,
            unavailable_cache_ttl_seconds=600.0,
            valkey=_CountingValkey(),
        )
        self.available = available
        self.probe_calls: dict[str, int] = {}

    async def aclose(self) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def _list_models_uncached(self, provider_id: str):
        self.probe_calls[provider_id] = self.probe_calls.get(provider_id, 0) + 1
        if not self.available:
            raise BifrostError("gateway_error", f"Provider {provider_id} unavailable")
        return [
            type(
                "ModelInfo",
                (),
                {
                    "id": f"{provider_id}/model-1",
                    "name": "model-1",
                    "supported_methods": ["chat_completion"],
                },
            )()
        ]

    async def chat_completion(self, *args, **kwargs):
        from agent_orchestrator.integrations.bifrost import ChatResponse

        return ChatResponse(content="done", tool_calls=[], raw={})


@pytest.mark.asyncio
async def test_providers_negatively_caches_unavailable_provider(tmp_path: Path):
    """A second /providers call must not re-probe a negatively-cached provider."""
    client = _NegativeCacheBifrostClient(available=False)
    app, engine = await build_test_app(tmp_path, bifrost_client=client)
    try:
        with TestClient(app) as http:
            first = http.get("/providers")
            second = http.get("/providers")
        assert first.status_code == 200
        assert second.status_code == 200
        providers = {p["provider_id"]: p for p in second.json()["providers"]}
        assert providers["openai"]["available"] is False
        assert "unavailable" in providers["openai"]["error"].lower()
        # Each provider was probed exactly once; the second call fast-failed from
        # the negative cache without hitting the slow underlying fetch.
        assert client.probe_calls == {"openai": 1, "gemini": 1}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_providers_refresh_forces_reprobe_of_now_available_provider(
    tmp_path: Path,
):
    """POST /providers/refresh clears the cache so a recovered provider re-probes."""
    client = _NegativeCacheBifrostClient(available=False)
    app, engine = await build_test_app(tmp_path, bifrost_client=client)
    try:
        with TestClient(app) as http:
            # Initial probe fails and is negatively cached.
            unavailable = http.get("/providers").json()["providers"]
            assert all(not p["available"] for p in unavailable)

            # Provider becomes available (API key added). Without a reset the
            # negative cache would still hide it.
            client.available = True
            still_cached = {
                p["provider_id"]: p for p in http.get("/providers").json()["providers"]
            }
            assert still_cached["openai"]["available"] is False

            # Reset the cache and re-probe.
            refresh = http.post("/providers/refresh")
            assert refresh.status_code == 200
            assert refresh.json()["status"] == "cleared"

            recovered = {
                p["provider_id"]: p for p in http.get("/providers").json()["providers"]
            }
        assert recovered["openai"]["available"] is True
        assert recovered["openai"]["models"] == ["openai/model-1"]
    finally:
        await engine.dispose()


def test_list_available_skills_returns_sorted_metadata_only(app):
    with TestClient(app) as client:
        response = client.get("/skills")

    assert response.status_code == 200
    skills = response.json()["skills"]
    assert [skill["name"] for skill in skills] == ["demo-skill"]
    assert "description" in skills[0]
    assert "metadata" in skills[0]
    assert "content_markdown" not in skills[0]


@pytest.mark.asyncio
async def test_list_providers_includes_prefixed_models_for_openrouter(tmp_path: Path):
    class OpenRouterModelBifrostClient(FakeBifrostClient):
        async def list_models(self, provider_id: str):
            if provider_id == "openrouter":
                model_ids = [
                    "openrouter/test-model",
                    "openai/gpt-4o-mini",
                    "openai/bagage-002",
                    "anthropic/claude-3-5-sonnet",
                    "google/gemini-2.0-flash",
                ]
                return [
                    type(
                        "ModelInfo",
                        (),
                        {
                            "id": model_id,
                            "name": model_id,
                            "supported_methods": ["chat_completion"],
                        },
                    )()
                    for model_id in model_ids
                ]
            return await super().list_models(provider_id)

    app, engine = await build_test_app(
        tmp_path,
        bifrost_client=OpenRouterModelBifrostClient(),
        enabled_provider_ids="openai,gemini,openrouter",
    )
    try:
        with TestClient(app) as client:
            response = client.get("/providers")
        assert response.status_code == 200
        providers = {item["provider_id"]: item for item in response.json()["providers"]}
        assert "openrouter" in providers
        assert providers["openrouter"]["models"] == ["openrouter/test-model"]
    finally:
        await engine.dispose()
