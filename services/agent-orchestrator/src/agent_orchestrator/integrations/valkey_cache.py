from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from agent_orchestrator.telemetry import get_tracer
from opentelemetry.trace import Status, StatusCode

tracer = get_tracer(__name__)


class _RespError(RuntimeError):
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
        raise _RespError("unexpected EOF from Valkey")
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
        raise _RespError((await _read_line(reader)).decode())
    raise _RespError(f"unknown RESP prefix: {prefix!r}")


@dataclass
class _RespConnection:
    host: str
    port: int
    username: str | None = None
    auth_token: str | None = None
    database: int = 0

    async def _execute(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *parts: object,
    ) -> Any:
        writer.write(_encode_resp_array([str(part) for part in parts]))
        await writer.drain()
        return await _read_resp(reader)

    async def execute(self, *parts: object) -> Any:
        command = str(parts[0]).upper() if parts else "UNKNOWN"
        span = tracer.start_span(
            "valkey.model_cache.execute",
            attributes={
                "db.system": "redis",
                "db.operation.name": command,
                "server.address": self.host,
                "server.port": self.port,
            },
        )
        writer: asyncio.StreamWriter | None = None
        skip_wait_closed = False
        try:
            reader, writer = await asyncio.open_connection(self.host, self.port)
            if self.auth_token:
                auth_parts = (
                    ("AUTH", self.username, self.auth_token)
                    if self.username
                    else ("AUTH", self.auth_token)
                )
                response = await self._execute(reader, writer, *auth_parts)
                if response != "OK":
                    raise _RespError("Valkey AUTH failed")
            if self.database:
                response = await self._execute(reader, writer, "SELECT", self.database)
                if response != "OK":
                    raise _RespError("Valkey SELECT failed")
            response = await self._execute(reader, writer, *parts)
        except GeneratorExit:
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


class ValkeyJsonCache:
    def __init__(
        self, url: str, *, key_prefix: str = "agent-orchestrator:model-cache:"
    ):
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        database = 0
        if parsed.path and parsed.path != "/":
            database = int(parsed.path.lstrip("/"))
        self._prefix = key_prefix
        self._conn = _RespConnection(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            username=parsed.username,
            auth_token=parsed.password,
            database=database,
        )

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get_json(self, key: str) -> Any | None:
        raw = await self._conn.execute("GET", self._key(key))
        return json.loads(raw) if raw is not None else None

    async def set_json(self, key: str, value: Any, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        payload = json.dumps(value)
        ttl_ms = max(1, int(ttl_seconds * 1000))
        await self._conn.execute("SET", self._key(key), payload, "PX", ttl_ms)
