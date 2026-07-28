from __future__ import annotations

import pytest

from eval_service.config import Settings


def test_defaults_are_secret_free():
    settings = Settings()
    assert settings.http_port == 4005
    assert settings.history_service_base_url == "http://localhost:4004"
    assert settings.bifrost_url == "http://localhost:4003"
    assert settings.evaluator_version == "eval-1"
    # No judge model by default -> not configured.
    assert settings.eval_judge_model == ""
    assert settings.judge_configured is False


def test_judge_configured_when_model_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "anthropic/claude-x")
    settings = Settings()
    assert settings.eval_judge_model == "anthropic/claude-x"
    assert settings.judge_configured is True


def test_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EVAL_DATABASE_URL", "postgresql+asyncpg://h/db")
    monkeypatch.setenv("HISTORY_SERVICE_BASE_URL", "http://history:4004")
    monkeypatch.setenv("EVAL_MAX_ATTEMPTS", "5")
    settings = Settings()
    assert settings.eval_database_url == "postgresql+asyncpg://h/db"
    assert settings.history_service_base_url == "http://history:4004"
    assert settings.eval_max_attempts == 5


def test_invalid_port_rejected():
    with pytest.raises(ValueError):
        Settings(http_port=0)


def test_invalid_max_attempts_rejected():
    with pytest.raises(ValueError):
        Settings(eval_max_attempts=0)


def test_invalid_concurrency_rejected():
    with pytest.raises(ValueError):
        Settings(eval_global_concurrency=0)
    with pytest.raises(ValueError):
        Settings(eval_per_game_concurrency=0)


def test_invalid_token_budget_rejected():
    with pytest.raises(ValueError):
        Settings(eval_judge_max_tokens=0)


def test_negative_backoff_rejected():
    with pytest.raises(ValueError):
        Settings(eval_retry_backoff_seconds=-1)


def test_max_targets_per_request_default_and_override(monkeypatch: pytest.MonkeyPatch):
    assert Settings().eval_max_targets_per_request == 200
    monkeypatch.setenv("EVAL_MAX_TARGETS_PER_REQUEST", "50")
    assert Settings().eval_max_targets_per_request == 50


def test_invalid_max_targets_rejected():
    with pytest.raises(ValueError):
        Settings(eval_max_targets_per_request=0)


def test_judge_input_caps_defaults_and_override(monkeypatch: pytest.MonkeyPatch):
    assert Settings().eval_judge_max_state_chars == 20_000
    assert Settings().eval_judge_max_round_moves == 100
    monkeypatch.setenv("EVAL_JUDGE_MAX_STATE_CHARS", "5000")
    monkeypatch.setenv("EVAL_JUDGE_MAX_ROUND_MOVES", "25")
    settings = Settings()
    assert settings.eval_judge_max_state_chars == 5000
    assert settings.eval_judge_max_round_moves == 25


def test_invalid_judge_input_caps_rejected():
    with pytest.raises(ValueError):
        Settings(eval_judge_max_state_chars=0)
    with pytest.raises(ValueError):
        Settings(eval_judge_max_round_moves=0)


def test_judge_key_name_defaults_to_eval_judge(monkeypatch: pytest.MonkeyPatch):
    # Judge traffic is pinned to a dedicated key by DEFAULT; opting out into the
    # game-playing key pool has to be spelled out.
    assert Settings().eval_judge_bifrost_key_name == "eval-judge"
    monkeypatch.setenv("EVAL_JUDGE_BIFROST_KEY_NAME", "judge-2")
    assert Settings().eval_judge_bifrost_key_name == "judge-2"


@pytest.mark.parametrize(
    ("model", "provider", "expected"),
    [
        # The model id prefix decides the provider whose key pool is drawn, so it
        # wins over the metadata-only EVAL_JUDGE_PROVIDER.
        ("openrouter/anthropic/claude-sonnet-4", "", "openrouter"),
        ("openrouter/anthropic/claude-sonnet-4", "anthropic", "openrouter"),
        ("gemini/gemini-2.5-pro", "", "gemini"),
        # No prefix -> fall back to the explicit provider setting.
        ("claude-x", "anthropic", "anthropic"),
        ("", "", ""),
    ],
)
def test_judge_routing_provider(model: str, provider: str, expected: str):
    settings = Settings(eval_judge_model=model, eval_judge_provider=provider)
    assert settings.judge_routing_provider == expected


def test_cors_origins_default_and_parse(monkeypatch: pytest.MonkeyPatch):
    default = Settings()
    assert "http://localhost:3001" in default.cors_allow_origins
    monkeypatch.setenv("EVAL_CORS_ALLOW_ORIGINS", "http://a.test , http://b.test ,")
    parsed = Settings().cors_allow_origins
    assert parsed == ["http://a.test", "http://b.test"]
