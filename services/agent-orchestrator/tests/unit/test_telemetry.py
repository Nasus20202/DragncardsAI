"""The agent-orchestrator's telemetry wiring.

The bootstrap itself (three providers, OTLP endpoints, the `OTEL_SDK_DISABLED`
no-op, shutdown flushing) is covered once in `services/shared`'s
`tests/test_telemetry.py`. What has to be pinned per service is that the service
actually calls it, with its own identity, at every edge it owns.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dragncards_common import telemetry as shared_telemetry

import agent_orchestrator.telemetry as telemetry
from agent_orchestrator.telemetry import TelemetryConfig, build_signal_endpoint


@pytest.fixture(autouse=True)
def reset_telemetry_globals():
    shared_telemetry._runtime = None
    shared_telemetry._httpx_instrumented = False
    shared_telemetry._logging_patched = False
    shared_telemetry._sqlalchemy_instrumented = False
    yield
    shared_telemetry._runtime = None
    shared_telemetry._httpx_instrumented = False
    shared_telemetry._logging_patched = False
    shared_telemetry._sqlalchemy_instrumented = False


def test_service_identity_defaults_to_agent_orchestrator(monkeypatch):
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    config = TelemetryConfig.from_env(telemetry.DEFAULT_SERVICE_NAME)

    assert telemetry.DEFAULT_SERVICE_NAME == "agent-orchestrator"
    assert config.service_name == "agent-orchestrator"


def test_telemetry_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-agent-orchestrator")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:55681")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    config = TelemetryConfig.from_env(telemetry.DEFAULT_SERVICE_NAME)

    assert config.service_name == "custom-agent-orchestrator"
    assert config.exporter_endpoint == "http://collector:55681"
    assert config.disabled is True


def test_build_signal_endpoint_appends_signal_path():
    assert (
        build_signal_endpoint("http://collector:4318", "traces")
        == "http://collector:4318/v1/traces"
    )
    assert (
        build_signal_endpoint("http://collector:4318/v1/metrics", "metrics")
        == "http://collector:4318/v1/metrics"
    )
    assert (
        build_signal_endpoint("http://collector:4318/v1/logs", "logs")
        == "http://collector:4318/v1/logs"
    )


def test_setup_telemetry_passes_the_service_name_to_the_shared_bootstrap(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        shared_telemetry,
        "setup_telemetry",
        lambda name: seen.append(name) or "runtime",
    )

    assert telemetry.setup_telemetry() == "runtime"
    assert seen == ["agent-orchestrator"]


def test_main_initializes_telemetry_before_serving(monkeypatch):
    from agent_orchestrator import main as main_module

    calls: list[str] = []
    monkeypatch.setattr(
        main_module, "setup_telemetry", lambda: calls.append("setup_telemetry")
    )
    monkeypatch.setattr(
        main_module, "create_app", lambda settings: calls.append("create_app")
    )
    monkeypatch.setattr(main_module, "mount_mcp", lambda app: calls.append("mount_mcp"))
    monkeypatch.setattr(
        main_module.uvicorn, "run", lambda app, host, port: calls.append("run")
    )

    main_module.main()

    assert calls == ["setup_telemetry", "create_app", "mount_mcp", "run"]


def test_instrument_fastapi_app_forwards_this_services_identity(monkeypatch):
    seen: list[tuple[object, str]] = []
    monkeypatch.setattr(
        shared_telemetry,
        "instrument_fastapi_app",
        lambda app, name: seen.append((app, name)),
    )
    app = SimpleNamespace(state=SimpleNamespace())

    telemetry.instrument_fastapi_app(app)

    assert seen == [(app, "agent-orchestrator")]


def test_create_engine_instruments_the_database_edge(monkeypatch):
    from agent_orchestrator.storage.db import create_engine

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    instrumentor_instance = MagicMock()
    monkeypatch.setattr(
        shared_telemetry,
        "_sqlalchemy_instrumentor",
        lambda: lambda: instrumentor_instance,
    )
    monkeypatch.setattr(
        shared_telemetry, "setup_telemetry", lambda name: SimpleNamespace(enabled=True)
    )

    engine = create_engine("sqlite+aiosqlite:///:memory:")

    instrumentor_instance.instrument.assert_called_once_with(engine=engine.sync_engine)


def test_valkey_client_carries_a_tracer_so_resp_spans_are_emitted():
    from agent_orchestrator.storage.valkey import RespConnection

    conn = RespConnection.from_url("redis://localhost:6381/0")

    assert conn._tracer is not None
