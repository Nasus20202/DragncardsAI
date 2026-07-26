from __future__ import annotations

import pytest

from history_service.config import Settings


def test_defaults_are_secret_free():
    settings = Settings()
    assert settings.history_ingest_stream == "history:ingest"
    assert settings.history_ingest_consumer_group == "history-service"
    assert settings.snapshot_every_n_events == 25
    assert settings.snapshot_max_interval_seconds == 300.0
    assert settings.http_port == 4004


def test_env_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SNAPSHOT_EVERY_N_EVENTS", "10")
    monkeypatch.setenv("HISTORY_INGEST_STREAM", "custom:ingest")
    monkeypatch.setenv("GAME_SERVICE_BASE_URL", "http://game:9")
    monkeypatch.setenv("AGENT_ORCHESTRATOR_BASE_URL", "http://orch:9")
    settings = Settings()
    assert settings.snapshot_every_n_events == 10
    assert settings.history_ingest_stream == "custom:ingest"
    assert settings.game_service_base_url == "http://game:9"
    assert settings.agent_orchestrator_base_url == "http://orch:9"


def test_rejects_invalid_snapshot_count():
    with pytest.raises(ValueError):
        Settings(snapshot_every_n_events=0)


def test_rejects_invalid_snapshot_interval():
    with pytest.raises(ValueError):
        Settings(snapshot_max_interval_seconds=0)


def test_rejects_invalid_maxlen():
    with pytest.raises(ValueError):
        Settings(history_ingest_stream_maxlen=0)


def test_lag_threshold_allows_zero():
    assert (
        Settings(
            history_consumer_lag_alert_threshold=0
        ).history_consumer_lag_alert_threshold
        == 0
    )
    with pytest.raises(ValueError):
        Settings(history_consumer_lag_alert_threshold=-1)


def test_consumer_name_falls_back_to_host_pid():
    settings = Settings(history_ingest_consumer_name="")
    assert ":" in settings.consumer_name
    explicit = Settings(history_ingest_consumer_name="worker-1")
    assert explicit.consumer_name == "worker-1"


def test_invalid_port_rejected():
    with pytest.raises(ValueError):
        Settings(http_port=0)
