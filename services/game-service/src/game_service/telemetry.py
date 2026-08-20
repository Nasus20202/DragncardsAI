from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from threading import Lock

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

DEFAULT_SERVICE_NAME = "game-service"
DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
DEFAULT_EXPORT_INTERVAL_MILLIS = 15_000
_LOG_FIELDS = " trace_id=%(trace_id)s span_id=%(span_id)s service=%(service_name)s"
_SENSITIVE_QUERY_PARAMETER = re.compile(
    r"([?&](?:data|authToken|session_token|password|token)=)[^&\s]+",
    re.IGNORECASE,
)


def _is_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def build_signal_endpoint(base_endpoint: str, signal: str) -> str:
    normalized = base_endpoint.rstrip("/")
    suffix = f"/v1/{signal}"
    if normalized.endswith(suffix):
        return normalized
    return f"{normalized}{suffix}"


@dataclass(frozen=True)
class TelemetryConfig:
    service_name: str
    exporter_endpoint: str
    disabled: bool
    export_interval_millis: int = DEFAULT_EXPORT_INTERVAL_MILLIS

    @classmethod
    def from_env(
        cls, default_service_name: str = DEFAULT_SERVICE_NAME
    ) -> "TelemetryConfig":
        return cls(
            service_name=os.environ.get("OTEL_SERVICE_NAME", default_service_name),
            exporter_endpoint=os.environ.get(
                "OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_OTLP_ENDPOINT
            ),
            disabled=_is_truthy(os.environ.get("OTEL_SDK_DISABLED")),
        )


@dataclass
class TelemetryRuntime:
    config: TelemetryConfig
    enabled: bool
    tracer_provider: TracerProvider | None = None
    meter_provider: MeterProvider | None = None
    logger_provider: LoggerProvider | None = None
    logging_handler: LoggingHandler | None = None

    def shutdown(self) -> None:
        if self.logging_handler is not None:
            logging.getLogger().removeHandler(self.logging_handler)
            self.logging_handler.close()
        if self.logger_provider is not None:
            self.logger_provider.shutdown()
        if self.meter_provider is not None:
            self.meter_provider.shutdown()
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()


_telemetry_lock = Lock()
_runtime: TelemetryRuntime | None = None
_httpx_instrumented = False
_logging_patched = False


def _sanitize_httpx_span(span, request) -> None:
    """Keep automatic HTTP spans free of query strings, bodies, and cookies."""
    url = request.url
    safe_url = f"{url.scheme}://{url.host}{url.path}"
    span.set_attribute("http.url", safe_url)
    span.set_attribute("url.full", safe_url)
    span.set_attribute("http.target", url.path)
    span.set_attribute("http.request.header.cookie", "<redacted>")


def _sanitize_log_value(value):
    if isinstance(value, str):
        return _SENSITIVE_QUERY_PARAMETER.sub(r"\1<redacted>", value)
    if value.__class__.__module__.startswith("httpx"):
        return _sanitize_log_value(str(value))
    if isinstance(value, tuple):
        return tuple(_sanitize_log_value(item) for item in value)
    if isinstance(value, list):
        return [_sanitize_log_value(item) for item in value]
    return value


def _patch_logging(service_name: str) -> None:
    global _logging_patched
    if _logging_patched:
        return

    previous_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
        record.msg = _sanitize_log_value(record.msg)
        record.args = _sanitize_log_value(record.args)
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            record.trace_id = format(span_context.trace_id, "032x")
            record.span_id = format(span_context.span_id, "016x")
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
        record.service_name = service_name
        return record

    logging.setLogRecordFactory(record_factory)

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        formatter = handler.formatter
        if formatter is None or "%(trace_id)s" in formatter._fmt:
            continue
        handler.setFormatter(
            logging.Formatter(formatter._fmt + _LOG_FIELDS, formatter.datefmt)
        )

    _logging_patched = True


def setup_telemetry(
    default_service_name: str = DEFAULT_SERVICE_NAME,
) -> TelemetryRuntime:
    global _runtime, _httpx_instrumented
    with _telemetry_lock:
        if _runtime is not None:
            return _runtime

        config = TelemetryConfig.from_env(default_service_name)
        _patch_logging(config.service_name)
        if config.disabled:
            _runtime = TelemetryRuntime(config=config, enabled=False)
            return _runtime

        resource = Resource.create({"service.name": config.service_name})
        trace_exporter = OTLPSpanExporter(
            endpoint=build_signal_endpoint(config.exporter_endpoint, "traces")
        )
        metric_exporter = OTLPMetricExporter(
            endpoint=build_signal_endpoint(config.exporter_endpoint, "metrics")
        )
        log_exporter = OTLPLogExporter(
            endpoint=build_signal_endpoint(config.exporter_endpoint, "logs")
        )

        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=config.export_interval_millis,
        )
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[metric_reader]
        )
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
        logging_handler = LoggingHandler(
            level=logging.NOTSET, logger_provider=logger_provider
        )

        trace.set_tracer_provider(tracer_provider)
        metrics.set_meter_provider(meter_provider)
        logging.getLogger().addHandler(logging_handler)

        if not _httpx_instrumented:
            HTTPXClientInstrumentor().instrument(request_hook=_sanitize_httpx_span)
            _httpx_instrumented = True

        _runtime = TelemetryRuntime(
            config=config,
            enabled=True,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            logging_handler=logging_handler,
        )
        return _runtime


def instrument_fastapi_app(app: FastAPI) -> None:
    runtime = setup_telemetry()
    if not runtime.enabled or getattr(app.state, "_otel_instrumented", False):
        return
    FastAPIInstrumentor.instrument_app(app)
    app.state._otel_instrumented = True


def shutdown_telemetry() -> None:
    global _runtime
    if _runtime is None or not _runtime.enabled:
        return
    _runtime.shutdown()
    _runtime = None


def get_tracer(name: str):
    return trace.get_tracer(name)
