from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from game_service.api.app import create_app
import game_service.telemetry as telemetry
from game_service.telemetry import TelemetryConfig, build_signal_endpoint


def test_telemetry_config_reads_env_overrides(monkeypatch):
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-game-service")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:9999")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    config = TelemetryConfig.from_env()

    assert config.service_name == "custom-game-service"
    assert config.exporter_endpoint == "http://collector:9999"
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


def test_create_app_skips_fastapi_instrumentation_when_disabled(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

    app = create_app()

    assert getattr(app.state, "_otel_instrumented", False) is False


def test_setup_telemetry_configures_otlp_log_export(monkeypatch):
    telemetry._runtime = None
    telemetry._httpx_instrumented = False
    telemetry._logging_patched = False
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")

    log_exporter = MagicMock()
    logger_provider = MagicMock()
    logging_handler = MagicMock()
    tracer_provider = MagicMock()
    meter_provider = MagicMock()
    root_logger = MagicMock(handlers=[])

    monkeypatch.setattr(telemetry, "OTLPSpanExporter", lambda endpoint: MagicMock())
    monkeypatch.setattr(telemetry, "OTLPMetricExporter", lambda endpoint: MagicMock())
    monkeypatch.setattr(
        telemetry,
        "OTLPLogExporter",
        lambda endpoint: (
            log_exporter if endpoint == "http://collector:4318/v1/logs" else None
        ),
    )
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
        telemetry,
        "LoggingHandler",
        lambda level, logger_provider: logging_handler,
    )
    monkeypatch.setattr(
        telemetry, "Resource", SimpleNamespace(create=lambda attrs: attrs)
    )
    monkeypatch.setattr(telemetry.trace, "set_tracer_provider", lambda provider: None)
    monkeypatch.setattr(telemetry.metrics, "set_meter_provider", lambda provider: None)
    monkeypatch.setattr(
        telemetry.HTTPXClientInstrumentor,
        "instrument",
        lambda self, **kwargs: None,
    )
    monkeypatch.setattr(
        telemetry.logging, "getLogger", lambda *args, **kwargs: root_logger
    )

    runtime = telemetry.setup_telemetry(default_service_name="game-service")

    assert runtime.enabled is True
    assert runtime.logger_provider is logger_provider
    assert runtime.logging_handler is logging_handler
    logger_provider.add_log_record_processor.assert_called_once()
    assert (
        logger_provider.add_log_record_processor.call_args.args[0].exporter
        is log_exporter
    )
    root_logger.addHandler.assert_called_once_with(logging_handler)

    telemetry.shutdown_telemetry()
    telemetry._httpx_instrumented = False
    telemetry._logging_patched = False


def test_httpx_span_hook_removes_query_and_cookie_data():
    span = MagicMock()
    request = SimpleNamespace(
        url=SimpleNamespace(
            scheme="https",
            host="engine",
            path="/new",
        )
    )

    telemetry._sanitize_httpx_span(span, request)

    span.set_attribute.assert_any_call("http.url", "https://engine/new")
    span.set_attribute.assert_any_call("url.full", "https://engine/new")
    span.set_attribute.assert_any_call("http.target", "/new")
    span.set_attribute.assert_any_call("http.request.header.cookie", "<redacted>")
