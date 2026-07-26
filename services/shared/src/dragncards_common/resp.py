"""Minimal per-command RESP (Valkey / Redis) client.

Each :meth:`RespConnection.execute` opens a fresh TCP connection, writes one RESP
command and reads a single reply, so the client is stateless between calls and
safe to share across subsystems. OpenTelemetry tracing is optional: pass a
``tracer`` to wrap each command in a ``valkey.execute`` span; without one the
client carries no telemetry dependency.
"""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse


class RespError(RuntimeError):
    pass


# Guards against a malformed or hostile reply advertising an absurd length that
# would otherwise drive an unbounded read/allocation or deep recursion. Valkey
# replies in this codebase (offsets, envelopes, small lists) sit far below these
# ceilings, so a value beyond them signals a corrupt/attacker-influenced frame.
_MAX_BULK_BYTES = 512 * 1024 * 1024  # per bulk string
_MAX_ARRAY_ITEMS = 10_000_000  # elements per array reply


def _encode_resp_array(parts: list[str]) -> bytes:
    payload = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        data = part.encode()
        payload.append(f"${len(data)}\r\n".encode())
        payload.append(data)
        payload.append(b"\r\n")
    return b"".join(payload)


async def _read_line(reader: asyncio.StreamReader) -> bytes:
    line = await reader.readline()
    if not line:
        raise RespError("unexpected EOF from Valkey")
    return line[:-2]


async def _read_resp(reader: asyncio.StreamReader) -> Any:
    prefix = await reader.readexactly(1)
    if prefix == b"+":
        return (await _read_line(reader)).decode()
    if prefix == b"-":
        raise RespError((await _read_line(reader)).decode())
    if prefix == b":":
        return int((await _read_line(reader)).decode())
    if prefix == b"$":
        length = int((await _read_line(reader)).decode())
        if length == -1:
            return None
        if length < 0 or length > _MAX_BULK_BYTES:
            raise RespError(f"bulk string length out of range: {length}")
        data = await reader.readexactly(length)
        await reader.readexactly(2)
        return data.decode()
    if prefix == b"*":
        length = int((await _read_line(reader)).decode())
        if length == -1:
            return None
        if length < 0 or length > _MAX_ARRAY_ITEMS:
            raise RespError(f"array length out of range: {length}")
        return [await _read_resp(reader) for _ in range(length)]
    raise RespError(f"unknown RESP prefix: {prefix!r}")


class RespConnection:
    """Stateless per-command RESP client over a fresh TCP connection.

    ``tracer`` is an optional OpenTelemetry tracer; when provided, each command
    is wrapped in a ``valkey.execute`` span carrying the usual ``db.*`` /
    ``server.*`` attributes. When ``None`` the client has no telemetry
    dependency at all.
    """

    def __init__(self, host: str, port: int, *, tracer: Any | None = None):
        self._host = host
        self._port = port
        self._tracer = tracer

    @classmethod
    def from_url(cls, url: str, *, tracer: Any | None = None) -> "RespConnection":
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        return cls(parsed.hostname or "localhost", parsed.port or 6379, tracer=tracer)

    async def aclose(self) -> None:
        """No-op today (per-command TCP); present for lifecycle consistency."""

    async def execute(self, *parts: object) -> Any:
        span = None
        status_cls = None
        status_code_cls = None
        if self._tracer is not None:
            # Soft import so consumers without OpenTelemetry never pull it in.
            from opentelemetry.trace import Status, StatusCode

            status_cls = Status
            status_code_cls = StatusCode
            command = str(parts[0]).upper() if parts else "UNKNOWN"
            span = self._tracer.start_span(
                "valkey.execute",
                attributes={
                    "db.system": "redis",
                    "db.operation.name": command,
                    "server.address": self._host,
                    "server.port": self._port,
                },
            )
        writer: asyncio.StreamWriter | None = None
        skip_wait_closed = False
        try:
            reader, writer = await asyncio.open_connection(self._host, self._port)
            writer.write(_encode_resp_array([str(part) for part in parts]))
            await writer.drain()
            response = await _read_resp(reader)
        except GeneratorExit:
            # Coroutine finalization cannot safely suspend for wait_closed().
            skip_wait_closed = True
            raise
        except BaseException as exc:
            if span is not None:
                span.record_exception(exc)
                if isinstance(exc, asyncio.CancelledError):
                    span.set_status(status_cls(status_code_cls.ERROR, "cancelled"))
                else:
                    span.set_status(status_cls(status_code_cls.ERROR, str(exc)))
            raise
        else:
            if span is not None:
                span.set_status(status_cls(status_code_cls.OK))
            return response
        finally:
            if writer is not None:
                writer.close()
                if not skip_wait_closed:
                    try:
                        await writer.wait_closed()
                    except Exception:
                        pass
            if span is not None:
                span.end()
