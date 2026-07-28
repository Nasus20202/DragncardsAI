from __future__ import annotations

import httpx
import pytest

from .api_test_support import INTEGRATION_ENABLED_PROVIDER_IDS


@pytest.mark.asyncio
async def test_catalog_endpoints_expose_available_providers_and_skills(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        providers_response = await client.get("/providers")
        skills_response = await client.get("/skills")

    assert providers_response.status_code == 200
    providers = providers_response.json()["providers"]
    provider_ids = [provider["provider_id"] for provider in providers]
    # The endpoint lists exactly the app's enabled providers, and the harness
    # pins that set so the assertion holds whichever providers the developer
    # running the suite has enabled.
    assert set(provider_ids) == set(app.state.settings.enabled_provider_ids)
    assert set(provider_ids) == set(INTEGRATION_ENABLED_PROVIDER_IDS.split(","))
    assert all("available" in provider for provider in providers)
    assert all("models" in provider for provider in providers)
    # The integration Bifrost stub cannot list models, so every enabled
    # provider is reported as unavailable with an error message.
    sample_provider = providers[0]
    assert sample_provider["available"] is False
    assert isinstance(sample_provider["models"], list)
    assert isinstance(sample_provider["error"], str)

    assert skills_response.status_code == 200
    skills = skills_response.json()["skills"]
    assert [skill["name"] for skill in skills] == ["test-skill"]


@pytest.mark.asyncio
async def test_ready_reports_runtime_checks(app):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] is True
    assert body["checks"]["bifrost"] is True
    assert body["checks"]["valkey"] is True
    assert body["checks"]["worker"] is True
    assert isinstance(body["http_port"], int)
