from __future__ import annotations

import pytest

from agent_orchestrator.config import Settings


def test_settings_parse_skill_roots():
    settings = Settings(SKILL_ROOTS="skills,/tmp/skills")
    assert [str(item) for item in settings.skill_roots] == ["skills", "/tmp/skills"]


def test_settings_require_provider_ids():
    with pytest.raises(ValueError):
        Settings(supported_provider_ids=("openai",))


def test_settings_validate_poll_interval():
    with pytest.raises(ValueError):
        Settings(worker_poll_interval_seconds=0)


def test_settings_validate_provider_models_cache_ttl():
    with pytest.raises(ValueError):
        Settings(provider_models_cache_ttl_seconds=-1)


def test_settings_parse_enabled_providers():
    settings = Settings(ENABLED_PROVIDER_IDS="openai,gemini")
    assert settings.enabled_provider_ids == ("openai", "gemini")


def test_settings_reject_unknown_enabled_provider():
    with pytest.raises(ValueError):
        Settings(ENABLED_PROVIDER_IDS="openai,unknown").enabled_provider_ids


def test_settings_parse_enabled_providers_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ENABLED_PROVIDER_IDS", "openrouter")
    settings = Settings()
    assert settings.enabled_provider_ids == ("openrouter",)


def test_settings_default_valkey_url():
    settings = Settings()
    assert settings.valkey_url == "redis://localhost:6381/0"
