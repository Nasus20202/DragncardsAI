from __future__ import annotations

import asyncio

import pytest

from dragncards_common.resp import RespConnection, RespError, _read_resp


class _FakeReader:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def readexactly(self, n: int) -> bytes:
        chunk = self._data[self._pos : self._pos + n]
        self._pos += n
        return chunk

    async def readline(self) -> bytes:
        idx = self._data.find(b"\r\n", self._pos)
        end = idx + 2
        line = self._data[self._pos : end]
        self._pos = end
        return line


async def test_read_resp_simple_string():
    assert await _read_resp(_FakeReader(b"+OK\r\n")) == "OK"


async def test_read_resp_error_prefix_raises():
    with pytest.raises(RespError) as exc:
        await _read_resp(_FakeReader(b"-ERR unknown command\r\n"))
    assert "ERR unknown command" in str(exc.value)


async def test_read_resp_integer_and_bulk_and_array():
    assert await _read_resp(_FakeReader(b":42\r\n")) == 42
    assert await _read_resp(_FakeReader(b"$3\r\nabc\r\n")) == "abc"
    assert await _read_resp(_FakeReader(b"$-1\r\n")) is None
    assert await _read_resp(_FakeReader(b"*2\r\n:1\r\n+two\r\n")) == [1, "two"]


async def test_read_resp_rejects_oversized_bulk_length():
    with pytest.raises(RespError) as exc:
        await _read_resp(_FakeReader(b"$999999999999\r\n"))
    assert "out of range" in str(exc.value)


async def test_read_resp_rejects_oversized_array_length():
    with pytest.raises(RespError) as exc:
        await _read_resp(_FakeReader(b"*999999999999\r\n"))
    assert "out of range" in str(exc.value)


async def test_read_resp_rejects_negative_bulk_length():
    with pytest.raises(RespError):
        await _read_resp(_FakeReader(b"$-5\r\n"))


def test_from_url_parses_host_and_port():
    conn = RespConnection.from_url("valkey://cache-host:6380")
    assert conn._host == "cache-host"
    assert conn._port == 6380


def test_from_url_rejects_unknown_scheme():
    with pytest.raises(ValueError):
        RespConnection.from_url("http://cache-host:6380")


async def test_execute_roundtrip_over_loopback():
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        await reader.readuntil(b"\r\n")  # command header; we only need to reply
        # Drain the rest of the request quickly, then reply +PONG.
        await asyncio.sleep(0)
        writer.write(b"+PONG\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        conn = RespConnection("127.0.0.1", port)
        assert await conn.execute("PING") == "PONG"
