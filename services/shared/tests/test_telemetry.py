from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from dragncards_common import telemetry
from dragncards_common.telemetry import TelemetryConfig, build_signal_endpoint


@pytest.fixture(autouse=True)
def reset_telemetry_globals():
    """Keep the module-level singletons out of each other's way.

    ``setup_telemetry`` is deliberately process-wide and idempotent, so a test
    that initialises it would otherwise decide the outcome of every later test.
    """
    telemetry._runtime = None
    telemetry._httpx_instrumented = False
    telemetry._logging_patched = False
    telemetry._sqlalchemy_instrumented = False
    yield
    telemetry._runtime = None
    telemetry._httpx_instrumented = False
    telemetry._logging_patched = False
    telemetry._sqlalchemy_instrumented = False


def test_config_defaults_to_the_callers_service_name(monkeypatch):
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)

    config = TelemetryConfig.from_env("history-service")

    assert config.service_name == "history-service"
    assert config.exporter_endpoint == telemetry.DEFAULT_OTLP_ENDPOINT
    assert config.disabled is False


def test_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-name")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:9999")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    config = TelemetryConfig.from_env("eval-service")

    assert config.service_name == "custom-name"
    assert config.exporter_endpoint == "http://collector:9999"
    assert config.disabled is True


def test_build_signal_endpoint_appends_signal_path_once():
    assert (
        build_signal_endpoint("http://collector:4318", "traces")
        == "http://collector:4318/v1/traces"
    )
    assert (
        build_signal_endpoint("http://collector:4318/", "metrics")
        == "http://collector:4318/v1/metrics"
    )
    assert (
        build_signal_endpoint("http://collector:4318/v1/logs", "logs")
        == "http://collector:4318/v1/logs"
    )


def test_setup_telemetry_is_a_no_op_when_sdk_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    def _fail(*args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("no exporter may be constructed when disabled")

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", _fail)
    monkeypatch.setattr(telemetry, "OTLPMetricExporter", _fail)
    monkeypatch.setattr(telemetry, "OTLPLogExporter", _fail)

    runtime = telemetry.setup_telemetry("history-service")

    assert runtime.enabled is False
    assert runtime.tracer_provider is None
    assert runtime.meter_provider is None
    assert runtime.logger_provider is None


def _stub_providers(monkeypatch, endpoint: str = "http://collector:4318"):
    """Replace the SDK pieces with recorders and return them."""
    recorded: dict[str, object] = {}

    def _record(signal):
        def factory(endpoint):
            recorded[signal] = endpoint
            return MagicMock()

        return factory

    tracer_provider = MagicMock()
    meter_provider = MagicMock()
    logger_provider = MagicMock()
    logging_handler = MagicMock()
    root_logger = MagicMock(handlers=[])

    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", endpoint)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.setattr(telemetry, "OTLPSpanExporter", _record("traces"))
    monkeypatch.setattr(telemetry, "OTLPMetricExporter", _record("metrics"))
    monkeypatch.setattr(telemetry, "OTLPLogExporter", _record("logs"))
    monkeypatch.setattr(telemetry, "TracerProvider", lambda resource: tracer_provider)
    monkeypatch.setattr(
        telemetry, "MeterProvider", lambda resource, metric_readers: meter_provider
    )
    monkeypatch.setattr(telemetry, "LoggerProvider", lambda resource: logger_provider)
    monkeypatch.setattr(telemetry, "BatchSpanProcessor", lambda exporter: MagicMock())
    monkeypatch.setattr(
        telemetry,
        "PeriodicExportingMetricReader",
        lambda exporter, export_interval_millis: MagicMock(),
    )
    monkeypatch.setattr(
        telemetry,
        "BatchLogRecordProcessor",
        lambda exporter: SimpleNamespace(exporter=exporter),
    )
    monkeypatch.setattr(
        telemetry, "LoggingHandler", lambda level, logger_provider: logging_handler
    )
    resources: dict[str, object] = {}
    monkeypatch.setattr(
        telemetry,
        "Resource",
        SimpleNamespace(create=lambda attrs: resources.setdefault("attrs", attrs)),
    )
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", lambda provider: None)
    monkeypatch.setattr(telemetry.metrics, "set_meter_provider", lambda provider: None)
    monkeypatch.setattr(
        telemetry.HTTPXClientInstrumentor, "instrument", lambda self: None
    )
    monkeypatch.setattr(
        telemetry.logging, "getLogger", lambda *args, **kwargs: root_logger
    )
    return SimpleNamespace(
        recorded=recorded,
        resources=resources,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        logging_handler=logging_handler,
        root_logger=root_logger,
    )


def test_setup_telemetry_wires_all_three_signals_with_service_identity(monkeypatch):
    stubs = _stub_providers(monkeypatch)

    runtime = telemetry.setup_telemetry("history-service")

    assert runtime.enabled is True
    assert runtime.tracer_provider is stubs.tracer_provider
    assert runtime.meter_provider is stubs.meter_provider
    assert runtime.logger_provider is stubs.logger_provider
    assert stubs.recorded == {
        "traces": "http://collector:4318/v1/traces",
        "metrics": "http://collector:4318/v1/metrics",
        "logs": "http://collector:4318/v1/logs",
    }
    assert stubs.resources["attrs"] == {"service.name": "history-service"}
    stubs.tracer_provider.add_span_processor.assert_called_once()
    stubs.logger_provider.add_log_record_processor.assert_called_once()
    stubs.root_logger.addHandler.assert_called_once_with(stubs.logging_handler)


def test_setup_telemetry_is_idempotent(monkeypatch):
    _stub_providers(monkeypatch)

    first = telemetry.setup_telemetry("history-service")
    second = telemetry.setup_telemetry("eval-service")

    assert first is second
    assert second.config.service_name == "history-service"


def test_instrument_fastapi_app_instruments_once(monkeypatch):
    _stub_providers(monkeypatch)
    instrumentor = MagicMock()
    monkeypatch.setattr(telemetry, "_fastapi_instrumentor", lambda: instrumentor)
    app = SimpleNamespace(state=SimpleNamespace())

    telemetry.instrument_fastapi_app(app, "history-service")
    telemetry.instrument_fastapi_app(app, "history-service")

    instrumentor.instrument_app.assert_called_once_with(app)
    assert app.state._otel_instrumented is True


def test_instrument_fastapi_app_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    instrumentor = MagicMock()
    monkeypatch.setattr(telemetry, "_fastapi_instrumentor", lambda: instrumentor)
    app = SimpleNamespace(state=SimpleNamespace())

    telemetry.instrument_fastapi_app(app, "history-service")

    instrumentor.instrument_app.assert_not_called()
    assert getattr(app.state, "_otel_instrumented", False) is False


def test_instrument_sqlalchemy_engine_uses_the_sync_engine_once(monkeypatch):
    _stub_providers(monkeypatch)
    instrumentor_instance = MagicMock()
    monkeypatch.setattr(
        telemetry, "_sqlalchemy_instrumentor", lambda: lambda: instrumentor_instance
    )
    engine = SimpleNamespace(sync_engine="sync-engine")

    telemetry.instrument_sqlalchemy_engine(engine, "history-service")
    telemetry.instrument_sqlalchemy_engine(engine, "history-service")

    instrumentor_instance.instrument.assert_called_once_with(engine="sync-engine")


def test_instrument_sqlalchemy_engine_skipped_when_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    instrumentor_instance = MagicMock()
    monkeypatch.setattr(
        telemetry, "_sqlalchemy_instrumentor", lambda: lambda: instrumentor_instance
    )

    telemetry.instrument_sqlalchemy_engine(
        SimpleNamespace(sync_engine="sync-engine"), "history-service"
    )

    instrumentor_instance.instrument.assert_not_called()


def test_shutdown_telemetry_flushes_every_provider(monkeypatch):
    stubs = _stub_providers(monkeypatch)

    telemetry.setup_telemetry("history-service")
    telemetry.shutdown_telemetry()

    stubs.logging_handler.close.assert_called_once()
    stubs.logger_provider.shutdown.assert_called_once()
    stubs.meter_provider.shutdown.assert_called_once()
    stubs.tracer_provider.shutdown.assert_called_once()
    assert telemetry._runtime is None
