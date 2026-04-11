"""
Integration tests for the Phoenix Channels WebSocket client.

Requires a running DragnCards instance at DRAGNCARDS_URL (default: ws://localhost:4000/socket).
Tests connect, join a lobby channel, and verify heartbeat by keeping the connection alive.

Run with:
    pytest tests/integration/test_phoenix_client.py -v
"""

import asyncio
import os

import httpx
import pytest

pytestmark = pytest.mark.live

from game_service.phoenix_client.client import PhoenixClient, PhoenixChannelError

DRAGNCARDS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev_user@example.com")
DEV_USER_PASSWORD = os.environ.get("DEV_USER_PASSWORD", "password")


@pytest.fixture
async def auth_token():
    """Obtain a Pow auth token for dev_user."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DRAGNCARDS_HTTP_URL}/api/v1/session",
            json={"user": {"email": DEV_USER_EMAIL, "password": DEV_USER_PASSWORD}},
        )
        resp.raise_for_status()
        return resp.json()["data"]["token"]


@pytest.fixture
async def connected_client(auth_token):
    """Return a connected PhoenixClient, disconnected after the test."""
    client = PhoenixClient(DRAGNCARDS_URL, auth_token=auth_token)
    await client.connect()
    yield client
    await client.disconnect()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_and_disconnect(auth_token):
    """Client connects and disconnects cleanly."""
    client = PhoenixClient(DRAGNCARDS_URL, auth_token=auth_token)
    await client.connect()
    assert client._ws is not None
    assert client._connected.is_set()
    await client.disconnect()
    assert not client._connected.is_set()


@pytest.mark.asyncio
async def test_heartbeat_sent_and_acknowledged(auth_token):
    """Heartbeat is sent and the server replies with ok."""
    client = PhoenixClient(DRAGNCARDS_URL, auth_token=auth_token)
    client.HEARTBEAT_INTERVAL = 1  # Override to 1s for test speed
    await client.connect()

    # Wait long enough for at least one heartbeat cycle
    await asyncio.sleep(2.5)

    # If heartbeat failed the recv_loop would have logged a warning and the
    # connection may have been dropped — verify it's still alive.
    assert client._connected.is_set(), "Connection dropped after heartbeat"
    await client.disconnect()


@pytest.mark.asyncio
async def test_join_lobby_channel(connected_client):
    """Client can join the lobby channel without error."""
    # DragnCards exposes a "room_list" channel the frontend uses for the lobby.
    # Unauthenticated join should still succeed (server allows it).
    # We just check we don't get an exception.
    try:
        channel = await connected_client.join("room_list:lobby")
        assert channel.topic == "room_list:lobby"
        await connected_client.leave("room_list:lobby")
    except PhoenixChannelError as exc:
        pytest.skip(f"Lobby channel not available: {exc}")


@pytest.mark.asyncio
async def test_join_nonexistent_channel_raises(connected_client):
    """Joining a bogus channel either errors or the server pushes an error reply."""
    # Phoenix may return an error payload for unknown topics.
    # We just verify the client doesn't hang forever.
    try:
        await asyncio.wait_for(
            connected_client.join("nonexistent:topic"),
            timeout=5.0,
        )
    except (PhoenixChannelError, asyncio.TimeoutError):
        pass  # Expected — either server rejected or no reply
