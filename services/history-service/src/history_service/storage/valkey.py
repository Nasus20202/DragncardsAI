from __future__ import annotations

from typing import Any

from dragncards_common.resp import RespConnection as _SharedRespConnection
from dragncards_common.resp import RespError

from history_service.telemetry import get_tracer

__all__ = ["RespConnection", "RespError"]

_tracer = get_tracer(__name__)


class RespConnection(_SharedRespConnection):
    """RESP client with the history-service OTEL tracer wired in.

    The shared :class:`dragncards_common.resp.RespConnection` only emits a
    ``valkey.execute`` span when it is handed a tracer, so without this subclass
    the ingest stream's Valkey traffic is invisible. Mirrors what the
    agent-orchestrator does for the same shared client.
    """

    def __init__(self, host: str, port: int, *, tracer: Any | None = None) -> None:
        # Default to this module's tracer while still accepting an explicit one,
        # so the inherited ``from_url`` classmethod (which forwards ``tracer=``)
        # does not raise ``TypeError`` on this subclass.
        super().__init__(host, port, tracer=tracer if tracer is not None else _tracer)
