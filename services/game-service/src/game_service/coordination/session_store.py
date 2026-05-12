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

from game_service.telemetry import get_tracer

tracer = get_tracer(__name__)


class SessionStore(Protocol):
    async def list_sessions(self) -> list[dict[str, Any]]: ...

    async def get_session(self, session_id: str) -> dict[str, Any] | None: ...

    async def put_session(self, record: dict[str, Any]) -> None: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def acquire_session_lock(
        self,
        session_id: str,
        owner_token: str,
        *,
        lease_ttl: float = 30.0,
        wait_timeout: float = 5.0,
        retry_interval: float = 0.05,
    ) -> bool: ...

    async def release_session_lock(self, session_id: str, owner_token: str) -> None: ...


class InMemorySessionStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._session_lock_tokens: dict[str, str] = {}
        self._session_locks_guard = asyncio.Lock()

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

    async def _get_session_lock(self, session_id: str) -> asyncio.Lock:
        async with self._session_locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._session_locks[session_id] = lock
            return lock

    async def acquire_session_lock(
        self,
        session_id: str,
        owner_token: str,
        *,
        lease_ttl: float = 30.0,
        wait_timeout: float = 5.0,
        retry_interval: float = 0.05,
    ) -> bool:
        del lease_ttl, retry_interval
        lock = await self._get_session_lock(session_id)
        try:
            await asyncio.wait_for(lock.acquire(), timeout=wait_timeout)
        except asyncio.TimeoutError:
            return False
        async with self._session_locks_guard:
            self._session_lock_tokens[session_id] = owner_token
        return True

    async def release_session_lock(self, session_id: str, owner_token: str) -> None:
        async with self._session_locks_guard:
            token = self._session_lock_tokens.get(session_id)
            lock = self._session_locks.get(session_id)
            if token != owner_token or lock is None:
                return
            self._session_lock_tokens.pop(session_id, None)
            if lock.locked():
                lock.release()


class _RespError(RuntimeError):
    pass


@dataclass
class _RespConnection:
    host: str
    port: int

    async def execute(self, *parts: object) -> Any:
        command = str(parts[0]).upper() if parts else "UNKNOWN"
        with tracer.start_as_current_span(
            "valkey.session_store.execute",
            attributes={
                "db.system": "redis",
                "db.operation.name": command,
                "server.address": self.host,
                "server.port": self.port,
            },
        ):
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
    def __init__(
        self,
        url: str,
        key_prefix: str = "game-service:session:",
        lock_prefix: str = "game-service:session-lock:",
    ) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "valkey"}:
            raise ValueError(f"Unsupported Valkey URL scheme: {parsed.scheme!r}")
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or 6379
        self._prefix = key_prefix
        self._lock_prefix = lock_prefix
        self._conn = _RespConnection(self._host, self._port)

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}{session_id}"

    def _lock_key(self, session_id: str) -> str:
        return f"{self._lock_prefix}{session_id}"

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
        await self._conn.execute(
            "SET", self._key(record["session_id"]), json.dumps(record)
        )

    async def delete_session(self, session_id: str) -> None:
        await self._conn.execute("DEL", self._key(session_id))

    async def acquire_session_lock(
        self,
        session_id: str,
        owner_token: str,
        *,
        lease_ttl: float = 30.0,
        wait_timeout: float = 5.0,
        retry_interval: float = 0.05,
    ) -> bool:
        key = self._lock_key(session_id)
        deadline = asyncio.get_running_loop().time() + wait_timeout
        ttl_ms = max(int(lease_ttl * 1000), 1)
        while True:
            result = await self._conn.execute(
                "SET", key, owner_token, "NX", "PX", str(ttl_ms)
            )
            if result == "OK":
                return True
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(retry_interval)

    async def release_session_lock(self, session_id: str, owner_token: str) -> None:
        key = self._lock_key(session_id)
        await self._conn.execute(
            "EVAL",
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            "1",
            key,
            owner_token,
        )
