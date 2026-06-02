from __future__ import annotations

import asyncio
from typing import Any

from agent_orchestrator.telemetry import get_tracer
from opentelemetry.trace import Status, StatusCode

tracer = get_tracer(__name__)


class RespError(RuntimeError):
    pass


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
    if prefix == b":":
        return int((await _read_line(reader)).decode())
    if prefix == b"$":
        length = int((await _read_line(reader)).decode())
        if length == -1:
            return None
        data = await reader.readexactly(length)
        await reader.readexactly(2)
        return data.decode()
    if prefix == b"*":
        length = int((await _read_line(reader)).decode())
        if length == -1:
            return None
        return [await _read_resp(reader) for _ in range(length)]
        if prefix == b"-":
            raise RespError((await _read_line(reader)).decode())
        raise RespError(f"unknown RESP prefix: {prefix!r}")


class RespConnection:
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port

    async def aclose(self) -> None:
        """No-op today (per-command TCP); present for lifecycle consistency."""

    async def execute(self, *parts: object) -> Any:
        command = str(parts[0]).upper() if parts else "UNKNOWN"
        span = tracer.start_span(
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
            span.record_exception(exc)
            if isinstance(exc, asyncio.CancelledError):
                span.set_status(Status(StatusCode.ERROR, "cancelled"))
            else:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        else:
            span.set_status(Status(StatusCode.OK))
            return response
        finally:
            if writer is not None:
                writer.close()
                if not skip_wait_closed:
                    await writer.wait_closed()
            span.end()
