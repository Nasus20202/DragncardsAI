from __future__ import annotations

import pytest
import yaml

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


def test_settings_job_event_stream_idle_block_is_independent_of_the_worker_tick():
    """The SSE fallback interval must not inherit the worker's job-claim tick.

    Reusing `worker_poll_interval_seconds` (0.2s) made every open stream issue
    five blocking Valkey reads and ten database queries a second for the whole
    life of a job.
    """
    settings = Settings()
    assert settings.job_event_stream_idle_block_seconds == 15.0
    assert (
        settings.job_event_stream_idle_block_seconds
        != settings.worker_poll_interval_seconds
    )
    assert (
        Settings(
            JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS=30
        ).job_event_stream_idle_block_seconds
        == 30
    )
    with pytest.raises(ValueError):
        Settings(job_event_stream_idle_block_seconds=0)


def test_settings_validate_provider_models_cache_ttl():
    with pytest.raises(ValueError):
        Settings(provider_models_cache_ttl_seconds=-1)


def test_settings_validate_bifrost_unavailable_cache_ttl():
    with pytest.raises(ValueError):
        Settings(bifrost_unavailable_cache_ttl_seconds=0)
    assert Settings().bifrost_unavailable_cache_ttl_seconds == 600.0
    assert (
        Settings(
            BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS=30
        ).bifrost_unavailable_cache_ttl_seconds
        == 30
    )


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


def test_settings_parse_game_service_mcp_url_from_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GAME_SERVICE_MCP_URL", "http://game-service:8000/mcp/")
    settings = Settings()
    assert settings.game_service_mcp_url == "http://game-service:8000/mcp/"


def test_root_compose_allows_game_service_mcp_url_override():
    with open("../../docker-compose.yaml", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    agent_orchestrator = payload["services"]["agent-orchestrator"]
    assert (
        agent_orchestrator["environment"]["GAME_SERVICE_MCP_URL"]
        == "${GAME_SERVICE_MCP_URL:-http://game-service:8000/mcp}"
    )


def test_automatic_continuation_defaults_are_on_and_bounded():
    settings = Settings()
    assert settings.auto_continue_truncated_turns is True
    assert settings.auto_continue_max_continuations == 3


def test_a_continuation_cap_below_one_is_rejected():
    """Zero would be a second way to spell "disabled", competing with the switch."""
    with pytest.raises(ValueError):
        Settings(AUTO_CONTINUE_MAX_CONTINUATIONS=0)
    with pytest.raises(ValueError):
        Settings(AUTO_CONTINUE_MAX_CONTINUATIONS=-1)


def test_automatic_continuation_can_be_switched_off_by_environment():
    assert (
        Settings(AUTO_CONTINUE_TRUNCATED_TURNS=False).auto_continue_truncated_turns
        is False
    )


def test_subagent_failsafe_settings_defaults_and_validation():
    """DRA-51: the subagent timeout is large and the counters are bounded."""
    settings = Settings()
    assert settings.subagent_timeout_seconds == 30 * 60.0
    assert settings.subagent_failsafe_max_consecutive_errors == 3
    assert settings.subagent_failsafe_max_empty_responses == 3

    assert Settings(SUBAGENT_TIMEOUT_SECONDS=60).subagent_timeout_seconds == 60
    assert (
        Settings(
            SUBAGENT_FAILSAFE_MAX_CONSECUTIVE_ERRORS=2
        ).subagent_failsafe_max_consecutive_errors
        == 2
    )
    assert (
        Settings(
            SUBAGENT_FAILSAFE_MAX_EMPTY_RESPONSES=5
        ).subagent_failsafe_max_empty_responses
        == 5
    )

    with pytest.raises(ValueError):
        Settings(subagent_timeout_seconds=0)
    with pytest.raises(ValueError):
        Settings(subagent_failsafe_max_consecutive_errors=0)
    with pytest.raises(ValueError):
        Settings(subagent_failsafe_max_empty_responses=0)
