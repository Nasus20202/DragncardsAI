from __future__ import annotations

import asyncio
import socket
import struct
import threading
import traceback

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


def _serve_once(mode: str, ready: threading.Event, port_box: list[int]) -> None:
    """A raw one-shot socket server that can abort the connection with a real RST.

    asyncio's own server cannot do this: the transport socket it exposes is a
    wrapper without ``close``/``setsockopt`` semantics we need, and a graceful
    close sends FIN rather than RST. ``SO_LINGER`` with a zero timeout is what
    makes the kernel emit RST, which is the packet that produces
    ``ConnectionResetError`` in the client.
    """
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    port_box.append(srv.getsockname()[1])
    srv.listen(1)
    ready.set()
    conn, _ = srv.accept()
    try:
        conn.recv(4096)
        if mode == "reply_then_reset":
            conn.sendall(b"$5\r\nhello\r\n")
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    finally:
        conn.close()
        srv.close()


async def _execute_against_resetting_server(mode: str):
    ready = threading.Event()
    port_box: list[int] = []
    thread = threading.Thread(target=_serve_once, args=(mode, ready, port_box))
    thread.start()
    try:
        assert ready.wait(5)
        conn = RespConnection("127.0.0.1", port_box[0])
        return await conn.execute("GET", "some-key")
    finally:
        thread.join(5)


async def test_execute_survives_a_reset_after_a_complete_reply():
    """A reset that lands only at close time must not fail a served command.

    The reply is already in hand, so tearing the socket down abortively is the
    server's business and not an error the caller should ever see.
    """
    assert await _execute_against_resetting_server("reply_then_reset") == "hello"


async def test_execute_reports_a_mid_command_reset_at_the_read_site():
    """A reset with no reply must surface, and blame the read -- not the close.

    Regression pin for DRA-35. asyncio stores ONE exception instance on the
    protocol and hands that same object to both the reader and the close waiter.
    Awaiting the close waiter in the ``finally`` therefore re-raised the very
    exception already propagating, and although that re-raise was caught and
    discarded, raising it had already grafted ``wait_closed`` frames onto the
    object's ``__traceback__``. The read failure then escaped carrying a
    traceback that ended at ``await writer.wait_closed()``, so a dead connection
    read like a cosmetic close error and sent everyone hunting the wrong line.
    """
    with pytest.raises(ConnectionResetError) as exc_info:
        await _execute_against_resetting_server("reset_before_reply")

    rendered = "".join(
        traceback.format_exception(
            type(exc_info.value), exc_info.value, exc_info.value.__traceback__
        )
    )
    # The traceback must point at the read that actually failed...
    assert "_read_resp" in rendered
    # ...and must not be decorated with the close-time frames, which is the whole
    # defect: they made the failure look like it originated in the cleanup path.
    assert "wait_closed" not in rendered


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
