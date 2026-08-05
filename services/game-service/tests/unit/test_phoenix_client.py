"""
Unit tests for game_service.phoenix_client.client

Pure tests — no network. Covers:
- PhxMessage.encode() / decode() round-trip
- PhxMessage handles None join_ref and ref
- PhoenixClient URL construction (token query param, vsn)
- PhoenixClient._next_ref() increments correctly
- Channel._handle() dispatches to registered handlers
- Channel._handle() queues state-update events
- Channel._handle() ignores unknown events (no queue)
"""

import asyncio
import json

import pytest

from game_service.phoenix_client.client import (
    ROOM_UNAVAILABLE_EVENT,
    Channel,
    PhoenixChannelError,
    PhoenixClient,
    PhxMessage,
)

# ---------------------------------------------------------------------------
# PhxMessage encode / decode
# ---------------------------------------------------------------------------


def test_phxmessage_encode_basic():
    msg = PhxMessage(
        join_ref="1", ref="2", topic="room:abc", event="game_action", payload={"x": 1}
    )
    encoded = msg.encode()
    parts = json.loads(encoded)
    assert parts == ["1", "2", "room:abc", "game_action", {"x": 1}]


def test_phxmessage_decode_basic():
    raw = json.dumps(["1", "2", "room:abc", "game_action", {"x": 1}])
    msg = PhxMessage.decode(raw)
    assert msg.join_ref == "1"
    assert msg.ref == "2"
    assert msg.topic == "room:abc"
    assert msg.event == "game_action"
    assert msg.payload == {"x": 1}


def test_phxmessage_roundtrip():
    original = PhxMessage(
        join_ref="3", ref="4", topic="phoenix", event="heartbeat", payload={}
    )
    decoded = PhxMessage.decode(original.encode())
    assert decoded.join_ref == original.join_ref
    assert decoded.ref == original.ref
    assert decoded.topic == original.topic
    assert decoded.event == original.event
    assert decoded.payload == original.payload


def test_phxmessage_none_refs():
    msg = PhxMessage(
        join_ref=None, ref=None, topic="phoenix", event="heartbeat", payload={}
    )
    parts = json.loads(msg.encode())
    assert parts[0] is None
    assert parts[1] is None


def test_phxmessage_decode_none_refs():
    raw = json.dumps([None, None, "phoenix", "heartbeat", {}])
    msg = PhxMessage.decode(raw)
    assert msg.join_ref is None
    assert msg.ref is None


def test_phxmessage_payload_can_be_list():
    msg = PhxMessage(join_ref=None, ref="1", topic="t", event="e", payload=[1, 2, 3])
    decoded = PhxMessage.decode(msg.encode())
    assert decoded.payload == [1, 2, 3]


def test_phxmessage_payload_can_be_string():
    msg = PhxMessage(join_ref=None, ref="1", topic="t", event="e", payload="hello")
    decoded = PhxMessage.decode(msg.encode())
    assert decoded.payload == "hello"


# ---------------------------------------------------------------------------
# PhoenixClient URL construction
# ---------------------------------------------------------------------------


def test_client_url_appends_websocket_path():
    client = PhoenixClient("ws://localhost:4000/socket")
    assert "/websocket" in client._url


def test_client_url_includes_vsn():
    client = PhoenixClient("ws://localhost:4000/socket")
    assert "vsn=2.0.0" in client._url


def test_client_url_includes_auth_token():
    client = PhoenixClient("ws://localhost:4000/socket", auth_token="mytoken")
    assert "authToken=mytoken" in client._url


def test_client_url_no_auth_token_omits_param():
    client = PhoenixClient("ws://localhost:4000/socket")
    assert "authToken" not in client._url


def test_client_url_preserves_existing_query_params():
    client = PhoenixClient("ws://localhost:4000/socket?foo=bar", auth_token="tok")
    assert "foo=bar" in client._url
    assert "authToken=tok" in client._url
    # Should use & not ? for second param
    assert "?foo=bar" in client._url


# ---------------------------------------------------------------------------
# PhoenixClient._next_ref
# ---------------------------------------------------------------------------


def test_next_ref_starts_at_one():
    client = PhoenixClient("ws://localhost:4000/socket")
    assert client._next_ref() == "1"


def test_next_ref_increments():
    client = PhoenixClient("ws://localhost:4000/socket")
    refs = [client._next_ref() for _ in range(5)]
    assert refs == ["1", "2", "3", "4", "5"]


def test_next_ref_returns_strings():
    client = PhoenixClient("ws://localhost:4000/socket")
    ref = client._next_ref()
    assert isinstance(ref, str)


# ---------------------------------------------------------------------------
# Channel._handle: event dispatch and state queue
# ---------------------------------------------------------------------------


def _make_channel() -> Channel:
    """Create a Channel without a real PhoenixClient connection."""
    client = PhoenixClient("ws://localhost:4000/socket")
    return Channel(topic="room:test", join_ref="1", client=client)


def test_channel_on_registers_handler():
    ch = _make_channel()
    received = []
    ch.on("my_event", lambda payload: received.append(payload))
    msg = PhxMessage(
        join_ref="1", ref="2", topic="room:test", event="my_event", payload={"k": "v"}
    )
    ch._handle(msg)
    assert received == [{"k": "v"}]


def test_channel_on_multiple_handlers_all_called():
    ch = _make_channel()
    results = []
    ch.on("ev", lambda p: results.append("a"))
    ch.on("ev", lambda p: results.append("b"))
    msg = PhxMessage(join_ref="1", ref=None, topic="room:test", event="ev", payload={})
    ch._handle(msg)
    assert results == ["a", "b"]


def test_channel_handle_unknown_event_no_error():
    ch = _make_channel()
    msg = PhxMessage(
        join_ref="1", ref=None, topic="room:test", event="unknown_event", payload={}
    )
    ch._handle(msg)  # Should not raise


def test_channel_handle_current_state_queued():
    ch = _make_channel()
    msg = PhxMessage(
        join_ref="1",
        ref=None,
        topic="room:test",
        event="current_state",
        payload={"game": {}},
    )
    ch._handle(msg)
    assert not ch._state_queue.empty()
    queued = ch._state_queue.get_nowait()
    assert queued.event == "current_state"
    assert queued.payload == {"game": {}}


def test_channel_handle_state_update_queued():
    ch = _make_channel()
    msg = PhxMessage(
        join_ref="1",
        ref=None,
        topic="room:test",
        event="state_update",
        payload={"delta": 1},
    )
    ch._handle(msg)
    assert not ch._state_queue.empty()


def test_channel_handle_send_update_queued():
    ch = _make_channel()
    msg = PhxMessage(
        join_ref="1", ref=None, topic="room:test", event="send_update", payload={}
    )
    ch._handle(msg)
    assert not ch._state_queue.empty()


def test_channel_handle_other_event_not_queued():
    ch = _make_channel()
    msg = PhxMessage(
        join_ref="1", ref=None, topic="room:test", event="presence_diff", payload={}
    )
    ch._handle(msg)
    assert ch._state_queue.empty()


def test_channel_handler_exception_does_not_propagate():
    ch = _make_channel()

    def bad_handler(payload):
        raise RuntimeError("handler error")

    ch.on("ev", bad_handler)
    msg = PhxMessage(join_ref="1", ref=None, topic="room:test", event="ev", payload={})
    ch._handle(msg)  # Should not raise


# ---------------------------------------------------------------------------
# Room refusal and join registration (DRA-36)
# ---------------------------------------------------------------------------


def test_channel_records_a_room_unavailable_push_without_a_handler():
    """The refusal must be observable without anyone having subscribed.

    DragnCards pushes it with the join, so a caller cannot register a handler in
    time — the receive loop can deliver it before `join()` has returned the
    Channel at all.
    """
    channel = Channel(
        topic="room:abc", join_ref="1", client=PhoenixClient("ws://x/socket")
    )
    assert channel.room_unavailable is False

    channel._handle(
        PhxMessage(
            join_ref="1",
            ref=None,
            topic="room:abc",
            event=ROOM_UNAVAILABLE_EVENT,
            payload={"reason": "missing_server_state"},
        )
    )

    assert channel.room_unavailable is True


def test_channel_does_not_report_a_refusal_for_an_ordinary_event():
    channel = Channel(
        topic="room:abc", join_ref="1", client=PhoenixClient("ws://x/socket")
    )
    channel._handle(
        PhxMessage(
            join_ref="1",
            ref=None,
            topic="room:abc",
            event="current_state",
            payload={"game": {}},
        )
    )
    assert channel.room_unavailable is False


@pytest.mark.asyncio
async def test_join_registers_the_channel_before_awaiting_the_reply():
    """A broadcast arriving with the join reply must not be dropped.

    `_dispatch` discards a message whose topic is not registered, and the receive
    loop is a separate task — so registering only after the reply loses the
    room's opening state broadcast and any refusal that replaces it.
    """
    client = PhoenixClient("ws://x/socket")
    seen: list[str] = []

    async def push_and_await(msg, reply_ref, timeout=10.0):
        # Stand in for the receive loop delivering the room's opening broadcast
        # in the window between the reply and this coroutine being rescheduled.
        client._dispatch(
            PhxMessage(
                join_ref=msg.join_ref,
                ref=None,
                topic=msg.topic,
                event="current_state",
                payload={"game": {"marker": "opening"}},
            )
        )
        seen.append("dispatched")
        return PhxMessage(
            join_ref=None,
            ref=reply_ref,
            topic=msg.topic,
            event="phx_reply",
            payload={"status": "ok", "response": {}},
        )

    client._push_and_await = push_and_await  # type: ignore[method-assign]

    channel = await client.join("room:abc")

    assert seen == ["dispatched"]
    state = await asyncio.wait_for(channel.wait_for_state_update(timeout=1.0), 2.0)
    assert state == {"game": {"marker": "opening"}}


@pytest.mark.asyncio
async def test_a_rejected_join_leaves_no_channel_registered():
    client = PhoenixClient("ws://x/socket")

    async def push_and_await(msg, reply_ref, timeout=10.0):
        return PhxMessage(
            join_ref=None,
            ref=reply_ref,
            topic=msg.topic,
            event="phx_reply",
            payload={"status": "error", "response": {"reason": "unauthorized"}},
        )

    client._push_and_await = push_and_await  # type: ignore[method-assign]

    with pytest.raises(PhoenixChannelError):
        await client.join("room:abc")

    assert "room:abc" not in client._channels


@pytest.mark.asyncio
async def test_a_join_that_raises_leaves_no_channel_registered():
    client = PhoenixClient("ws://x/socket")

    async def push_and_await(msg, reply_ref, timeout=10.0):
        raise asyncio.TimeoutError

    client._push_and_await = push_and_await  # type: ignore[method-assign]

    with pytest.raises(asyncio.TimeoutError):
        await client.join("room:abc")

    assert "room:abc" not in client._channels
