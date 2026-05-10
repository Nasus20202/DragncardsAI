"""Session coordination storage backends.

The game-service uses this abstraction to keep session metadata outside the
process. A lightweight Valkey-backed store is used in local runtime, while an
in-memory fallback keeps tests and isolated unit runs simple.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse


class SessionStore(Protocol):
    async def list_sessions(self) -> list[dict[str, Any]]: ...

    async def get_session(self, session_id: str) -> dict[str, Any] | None: ...

    async def put_session(self, record: dict[str, Any]) -> None: ...

    async def delete_session(self, session_id: str) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def list_sessions(self) -> list[dict[str, Any]]:
        async with self._lock:
            return list(self._records.values())

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        async with self._lock:
            record = self._records.get(session_id)
            return dict(record) if record is not None else None

    async def put_session(self, record: dict[str, Any]) -> None:
        session_id = record["session_id"]
        async with self._lock:
            self._records[session_id] = dict(record)

    async def delete_session(self, session_id: str) -> None:
        async with self._lock:
            self._records.pop(session_id, None)


class _RespError(RuntimeError):
    pass


@dataclass
class _RespConnection:
    host: str
    port: int

    async def execute(self, *parts: object) -> Any:
        reader, writer = await asyncio.open_connection(self.host, self.port)
        try:
            writer.write(_encode_resp_array([str(part) for part in parts]))
            await writer.drain()
            return await _read_resp(reader)
        finally:
            writer.close()
            await writer.wait_closed()


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


class ValkeySessionStore:
    def __init__(self, url: str, key_prefix: str = "game-service:session:") -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 6379
        self._prefix = key_prefix
        self._conn = _RespConnection(self._host, self._port)

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    async def list_sessions(self) -> list[dict[str, Any]]:
        keys = await self._conn.execute("KEYS", f"{self._prefix}*")
        if not keys:
            return []
        records: list[dict[str, Any]] = []
        for key in keys:
            raw = await self._conn.execute("GET", key)
            if raw is None:
                continue
            records.append(json.loads(raw))
        records.sort(key=lambda item: item["created_at"])
        return records

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        raw = await self._conn.execute("GET", self._key(session_id))
        return json.loads(raw) if raw is not None else None

    async def put_session(self, record: dict[str, Any]) -> None:
        await self._conn.execute("SET", self._key(record["session_id"]), json.dumps(record))

    async def delete_session(self, session_id: str) -> None:
        await self._conn.execute("DEL", self._key(session_id))
