from __future__ import annotations

import pytest

from agent_orchestrator.storage.valkey import RespConnection


class _ExplodingReader:
    async def readexactly(self, _: int) -> bytes:
        raise GeneratorExit


class _FakeWriter:
    def __init__(self) -> None:
        self.closed = False
        self.wait_closed_awaited = False

    def write(self, _: bytes) -> None:
        return None

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        self.wait_closed_awaited = True


@pytest.mark.asyncio
async def test_resp_connection_skips_wait_closed_during_generator_exit(monkeypatch):
    writer = _FakeWriter()

    async def fake_open_connection(host: str, port: int):
        assert host == "localhost"
        assert port == 6379
        return _ExplodingReader(), writer

    monkeypatch.setattr(
        "dragncards_common.resp.asyncio.open_connection",
        fake_open_connection,
    )

    conn = RespConnection("localhost", 6379)

    with pytest.raises(GeneratorExit):
        await conn.execute("PING")

    assert writer.closed is True
    assert writer.wait_closed_awaited is False
