from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .app_test_support import FakeBifrostClient, build_test_app


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
    with TestClient(app) as client:
        response = client.get("/providers")
    assert response.status_code == 200
    providers = response.json()["providers"]
    provider_ids = {item["provider_id"] for item in providers}
    assert provider_ids == {"openai", "gemini"}
    providers_by_id = {item["provider_id"]: item for item in providers}
    assert providers_by_id["openai"]["models"] == ["gpt-4o-mini", "gpt-4.1-mini"]
    assert providers_by_id["gemini"]["models"] == ["gemini-2.0-flash"]
    assert providers_by_id["openai"]["available"] is True
    assert providers_by_id["openai"]["error"] is None


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
        assert providers["openai"]["models"] == ["gpt-4o-mini", "openai/gpt-4.1-mini"]
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
                "models": [
                    "qwen3.5-0.8b",
                    "lmstudio/backup-local-model",
                ],
                "available": True,
                "error": None,
            }
        ]
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
