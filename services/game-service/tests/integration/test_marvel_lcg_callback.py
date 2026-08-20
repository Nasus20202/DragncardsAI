"""Cross-layer callback coverage for Marvel LCG transport degradation."""

from __future__ import annotations

import pytest

from game_service.logic.exceptions import StateUnavailableError
from game_service.logic.session import GameSession
from game_service.marvel_lcg.frames import MarvelLcgRenderSocket
from game_service.marvel_lcg.platform import MarvelLcgPlatform


@pytest.mark.asyncio
async def test_reconnect_exhaustion_announces_through_platform_into_session():
    """Exercise RenderSocket -> platform -> GameSession, without a live engine."""

    class BrokenSocket:
        async def recv(self):
            raise ConnectionError("socket closed")

    async def always_broken(*args, **kwargs):
        raise OSError("cannot reconnect")

    platform = MarvelLcgPlatform("http://engine", "password", http_client=object())
    session = GameSession(
        session_id="session-1",
        platform="marvel-lcg",
        driver=platform,
        initial_state={"ready": True},
    )
    socket = MarvelLcgRenderSocket(
        "ws://engine/ws",
        seat=0,
        websocket_factory=always_broken,
        on_frame=platform._on_background_frame,
        reconnect_attempts=1,
    )
    socket._socket = BrokenSocket()

    try:
        await socket._read_loop()

        assert socket.frames.latest is not None
        assert socket.frames.latest.transport_degraded
        assert 0 in platform._degraded_seats
        assert session._state_unavailable
        assert session._state_stale
        with pytest.raises(StateUnavailableError):
            await session.get_state()
    finally:
        await socket.close()
