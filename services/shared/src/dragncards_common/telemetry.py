"""OpenTelemetry bootstrap shared by the first-party Python services.

Every first-party Python service needs the same three providers (traces,
metrics, logs), the same OTLP/HTTP exporters, the same ``service.name`` resource
and the same "``OTEL_SDK_DISABLED=true`` must be a no-op" behaviour. That setup
used to be copy-pasted per service, which is exactly how a newly added service
ends up emitting nothing at all: nobody remembers to copy it. It lives here so a
new service wires telemetry by calling these helpers with its own service name.

Call ``setup_telemetry(<service-name>)`` once per process (as early as possible,
before the app is built), then ``instrument_fastapi_app`` for the HTTP server
edge, ``instrument_sqlalchemy_engine`` for the database edge, and pass
``get_tracer(__name__)`` into :class:`dragncards_common.resp.RespConnection` for
the Valkey edge. ``shutdown_telemetry`` flushes the exporters on shutdown.

Configuration is read from the standard OpenTelemetry environment variables
(``OTEL_SERVICE_NAME``, ``OTEL_EXPORTER_OTLP_ENDPOINT``, ``OTEL_SDK_DISABLED``,
and — via ``Resource.create`` — ``OTEL_RESOURCE_ATTRIBUTES``) so the same code
runs unchanged in Docker Compose and in a direct local run.

Only IDs, names, counts and outcomes belong on a span. Never attach a prompt,
a message body, a recorded game state or any credential: telemetry leaves the
process and is readable by anyone with access to the collector.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from threading import Lock
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

DEFAULT_OTLP_ENDPOINT = "http://localhost:4318"
DEFAULT_EXPORT_INTERVAL_MILLIS = 15_000
_LOG_FIELDS = " trace_id=%(trace_id)s span_id=%(span_id)s service=%(service_name)s"

__all__ = [
    "DEFAULT_EXPORT_INTERVAL_MILLIS",
    "DEFAULT_OTLP_ENDPOINT",
    "TelemetryConfig",
    "TelemetryRuntime",
    "build_signal_endpoint",
    "get_tracer",
    "instrument_fastapi_app",
    "instrument_sqlalchemy_engine",
    "setup_telemetry",
    "shutdown_telemetry",
]


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
    def from_env(cls, default_service_name: str) -> "TelemetryConfig":
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
_sqlalchemy_instrumented = False


def _fastapi_instrumentor() -> Any:
    """Import the FastAPI instrumentor lazily.

    ``opentelemetry.instrumentation.fastapi`` imports ``fastapi`` at module
    level, and this library is also used by code paths that have no web
    framework. Importing it here keeps ``dragncards_common`` usable without
    FastAPI installed, and gives tests a single seam to stub.
    """
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    return FastAPIInstrumentor


def _sqlalchemy_instrumentor() -> Any:
    """Import the SQLAlchemy instrumentor lazily, for the same reason."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    return SQLAlchemyInstrumentor


def _patch_logging(service_name: str) -> None:
    global _logging_patched
    if _logging_patched:
        return

    previous_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = previous_factory(*args, **kwargs)
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


def setup_telemetry(default_service_name: str) -> TelemetryRuntime:
    """Initialise traces, metrics and logs export for this process.

    Idempotent: the first call wins and later calls return the same runtime, so
    a service may call it from both its entrypoint and its app factory.
    """
    global _runtime, _httpx_instrumented
    with _telemetry_lock:
        if _runtime is not None:
            return _runtime

        config = TelemetryConfig.from_env(default_service_name)
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
            HTTPXClientInstrumentor().instrument()
            _httpx_instrumented = True

        _patch_logging(config.service_name)
        _runtime = TelemetryRuntime(
            config=config,
            enabled=True,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            logging_handler=logging_handler,
        )
        return _runtime


def instrument_fastapi_app(app: Any, default_service_name: str) -> None:
    """Instrument a FastAPI app's server edge, once per app."""
    runtime = setup_telemetry(default_service_name)
    if not runtime.enabled or getattr(app.state, "_otel_instrumented", False):
        return
    _fastapi_instrumentor().instrument_app(app)
    app.state._otel_instrumented = True


def instrument_sqlalchemy_engine(engine: Any, default_service_name: str) -> None:
    """Instrument an async SQLAlchemy engine's underlying sync engine, once."""
    global _sqlalchemy_instrumented
    runtime = setup_telemetry(default_service_name)
    if not runtime.enabled or _sqlalchemy_instrumented:
        return
    instrumentor_cls = _sqlalchemy_instrumentor()
    instrumentor_cls().instrument(engine=engine.sync_engine)
    _sqlalchemy_instrumented = True


def shutdown_telemetry() -> None:
    global _runtime
    if _runtime is None or not _runtime.enabled:
        return
    _runtime.shutdown()
    _runtime = None


def get_tracer(name: str):
    return trace.get_tracer(name)
