"""OpenTelemetry wiring for the history-service.

The bootstrap itself lives in :mod:`dragncards_common.telemetry` and is shared
with the other first-party Python services; this module only binds this
service's ``service.name`` default so call sites here read the same as they do
elsewhere and the name is stated in exactly one place.

Never attach a recorded event payload, a game state, or a Valkey value to a
span: telemetry leaves the process, and a recorded game state is exactly the
kind of content that must not.
"""

from __future__ import annotations

from typing import Any

from dragncards_common import telemetry as _telemetry
from dragncards_common.telemetry import (
    TelemetryConfig,
    TelemetryRuntime,
    build_signal_endpoint,
    get_tracer,
    shutdown_telemetry,
)

DEFAULT_SERVICE_NAME = "history-service"

__all__ = [
    "DEFAULT_SERVICE_NAME",
    "TelemetryConfig",
    "TelemetryRuntime",
    "build_signal_endpoint",
    "get_tracer",
    "instrument_fastapi_app",
    "instrument_sqlalchemy_engine",
    "setup_telemetry",
    "shutdown_telemetry",
]


def setup_telemetry(
    default_service_name: str = DEFAULT_SERVICE_NAME,
) -> TelemetryRuntime:
    return _telemetry.setup_telemetry(default_service_name)


def instrument_fastapi_app(app: Any) -> None:
    _telemetry.instrument_fastapi_app(app, DEFAULT_SERVICE_NAME)


def instrument_sqlalchemy_engine(engine: Any) -> None:
    _telemetry.instrument_sqlalchemy_engine(engine, DEFAULT_SERVICE_NAME)
