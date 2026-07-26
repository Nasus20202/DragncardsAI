from __future__ import annotations

from typing import Any

from agent_orchestrator.telemetry import get_tracer
from dragncards_common.resp import RespConnection as _SharedRespConnection
from dragncards_common.resp import RespError

__all__ = ["RespConnection", "RespError"]

_tracer = get_tracer(__name__)


class RespConnection(_SharedRespConnection):
    """RESP client with the agent-orchestrator OTEL tracer wired in.

    Delegates to the shared :class:`dragncards_common.resp.RespConnection`,
    supplying this module's tracer so every command is emitted as a
    ``valkey.execute`` span (matching the previous behavior).
    """

    def __init__(self, host: str, port: int, *, tracer: Any | None = None) -> None:
        # Default to this module's tracer, but accept an explicit one so the
        # inherited ``from_url`` classmethod (which forwards ``tracer=``) does
        # not raise ``TypeError`` when used on this subclass.
        super().__init__(host, port, tracer=tracer if tracer is not None else _tracer)
