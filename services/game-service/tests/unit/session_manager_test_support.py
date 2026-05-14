from __future__ import annotations

from datetime import datetime, timezone

from game_service.logic.session import GameSession
from game_service.phoenix_client.client import Channel, PhoenixClient, PhxMessage


def make_channel() -> Channel:
    client = PhoenixClient("ws://localhost:4000/socket")
    return Channel(topic="room:test", join_ref="1", client=client)


def make_session(channel: Channel | None = None) -> GameSession:
    channel = channel or make_channel()
    client = PhoenixClient("ws://localhost:4000/socket")
    return GameSession(
        session_id="test-session",
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug="test-room",
        created_at=datetime.now(timezone.utc),
        client=client,
        channel=channel,
    )


def fire_event(channel: Channel, event: str, payload: dict) -> None:
    message = PhxMessage(
        join_ref="1", ref=None, topic="room:test", event=event, payload=payload
    )
    channel._handle(message)
