"""OpenTelemetry wiring for the eval-service.

The bootstrap itself lives in :mod:`dragncards_common.telemetry` and is shared
with the other first-party Python services; this module only binds this
service's ``service.name`` default so call sites here read the same as they do
elsewhere and the name is stated in exactly one place.

This service handles the two most sensitive payloads in the repository — the
judge prompt and the recorded game state it is assembled from. Neither, nor any
part of either, nor a judge's raw response, may ever become a span attribute.
Spans here carry identifiers, scopes, counts and outcomes only.
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

DEFAULT_SERVICE_NAME = "eval-service"

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
