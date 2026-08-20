from __future__ import annotations

import asyncio
import gzip
import json
import logging
from unittest.mock import AsyncMock, MagicMock, call
from urllib.parse import quote, unquote

import httpx
import pytest

from game_service.coordination.history_emitter import NullHistoryEmitter
from game_service.logic.exceptions import (
    EnumeratedOptionError,
    PlatformTransportError,
    SessionError,
    StateUnavailableError,
)
from game_service.logic.session import GameSession
from game_service.marvel_lcg.client import (
    MarvelLcgAuthenticationError,
    MarvelLcgHttpError,
    MarvelLcgHttpClient,
    NewGameDescriptor,
)
from game_service.marvel_lcg.frames import (
    FrameBuffer,
    FrameDescriptor,
    MarvelLcgRenderSocket,
    PERMITTED_DRIVER_TELEMETRY_ATTRIBUTE_KEYS,
    PERMITTED_SOCKET_TELEMETRY_ATTRIBUTE_KEYS,
    PromptAttemptGuard,
    PromptSignature,
    StuckPromptError,
)
from game_service.marvel_lcg.normalizer import MarvelLcgNormaliser
from game_service.marvel_lcg.options import build_options
from game_service.marvel_lcg.platform import MarvelLcgPlatform
import game_service.marvel_lcg.client as client_module
import game_service.marvel_lcg.frames as frames_module
import game_service.marvel_lcg.platform as platform_module
import game_service.telemetry as telemetry


def test_frame_descriptor_parses_nested_notifications_and_game_over():
    frame = FrameDescriptor.from_payload(
        {
            "render_id": -1,
            "game_id": 3,
            "ask_players": [0],
            "remaining_time": 0,
            "max_timeout": 0,
            "notify_texts": ['{"text":"done"}'],
            "debug_message": "",
            "current_step_id": 4,
            "max_replay_step_id": 4,
            "player_id": 0,
            "total_players": 1,
        }
    )
    assert frame.game_over
    assert frame.notify_texts == ({"text": "done"},)


def test_marvel_platform_rejects_missing_or_unsafe_urls_and_passwords():
    with pytest.raises(ValueError, match="PASSWORD"):
        MarvelLcgPlatform("http://engine", "")
    with pytest.raises(ValueError, match="query"):
        MarvelLcgHttpClient("http://engine?debug=1", "password")
    with pytest.raises(ValueError, match="debug"):
        MarvelLcgHttpClient("http://engine/debug", "password")


async def test_terminal_frame_is_terminal_not_bad_state():
    platform = MarvelLcgPlatform("http://engine", "password", http_client=object())
    terminal: list[dict] = []
    platform.register_state_handlers(on_terminal=terminal.append)
    await platform._process_frame(FrameDescriptor(-1, 1, (), 0, 0, (), "", 1, 1, 0, 1))
    assert platform._terminal
    assert terminal == [{"render_id": -1}]
    with pytest.raises(SessionError, match="terminal"):
        platform.ensure_move_allowed()


def _option_client(*, prompt: str = "Pick one", world=None):
    client = MagicMock()
    client.get_world = AsyncMock(
        return_value=world
        or {
            "round_id": 1,
            "phase": "Player 1 Turn",
            "players": [],
        }
    )
    client.get_ask = AsyncMock(
        return_value={
            "prompt_text": prompt,
            "options": [
                {
                    "id": 7,
                    "name": "Play",
                    "target_num_range": [0, 0],
                }
            ],
        }
    )
    client.client_updated = AsyncMock()
    client.post = AsyncMock()
    return client


def _option_platform(client, *, seats=("player1",), max_submission_attempts=3):
    platform = MarvelLcgPlatform(
        "http://engine",
        "password",
        seats=seats,
        max_submission_attempts=max_submission_attempts,
        http_client=client,
    )
    socket = MagicMock()
    socket.wait_for_frame = AsyncMock(
        return_value=FrameDescriptor(1, 1, (), 0, 0, (), "", 1, 1, 0, 1)
    )
    platform._socket = socket
    platform._sockets[seats[0]] = socket
    return platform


class _RecordedSpan:
    def __init__(self, name, initial, sink):
        self.name = name
        self.attributes = dict(initial or {})
        self.events: list[dict] = []
        self.sink = sink

    def __enter__(self):
        self.sink.append(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_value is not None:
            self.events.append(
                {
                    "name": "exception",
                    "attributes": {
                        "exception.type": type(exc_value).__name__,
                        "exception.message": str(exc_value),
                    },
                }
            )
        return False

    def set_attribute(self, key, value):
        self.attributes[key] = value


class _RecordedTracer:
    def __init__(self):
        self.spans = []

    def start_as_current_span(self, name, attributes=None):
        return _RecordedSpan(name, attributes, self.spans)


class _PlatformHistory:
    def __init__(self):
        self.events: list[dict] = []

    async def emit_platform_event(self, **event):
        self.events.append(event)


async def test_application_spans_cover_game_creation_options_and_submission(
    monkeypatch,
):
    recorded = _RecordedTracer()
    monkeypatch.setattr(platform_module, "tracer", recorded)
    monkeypatch.setattr(client_module, "tracer", recorded)
    client = _option_client()
    client.list_scenarios = AsyncMock(return_value=["scenario.json"])
    client.list_starter_deck = AsyncMock(return_value=["hero.json"])
    client.get_scenario_json = AsyncMock(return_value="{}")
    client.get_hero_json = AsyncMock(return_value="{}")
    client.new_game = AsyncMock(return_value={"result": "New game created"})
    platform = _option_platform(client)

    await platform.create_table(MagicMock(), {})
    options = await platform.list_options("player1")
    await platform.choose_option(
        "player1",
        option_id=7,
        prompt_id=options.prompt_id,
        prompt_version=options.prompt_version,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/get_version":
            return httpx.Response(
                200, content=b"v-test", headers={"content-type": "text/plain"}
            )
        return httpx.Response(
            200,
            json={"prompt_text": "Pick one", "options_json": "[]"},
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(
        base_url="http://engine", transport=httpx.MockTransport(handler)
    ) as raw:
        await MarvelLcgHttpClient("http://engine", "password", client=raw).get_ask()

    names = {span.name for span in recorded.spans}
    assert PERMITTED_DRIVER_TELEMETRY_ATTRIBUTE_KEYS == {
        "game.action.name",
        "game.platform",
        "game.seat",
        "game.seat.count",
        "game.attempt",
        "game.outcome",
        "error.type",
        "game.hero.count",
        "game.encounter_set.count",
        "game.option.count",
        "game.prompt.present",
        "game.option.id",
        "game.target.count",
        "game.resource.count",
        "http.request.method",
        "http.route",
    }
    assert {
        "marvel_lcg.create_game",
        "marvel_lcg.world",
        "marvel_lcg.ask",
        "marvel_lcg.read_options",
        "marvel_lcg.submit_option",
    } <= names
    for span in recorded.spans:
        assert set(span.attributes) <= PERMITTED_DRIVER_TELEMETRY_ATTRIBUTE_KEYS
        assert all(
            not isinstance(value, (dict, list, tuple))
            for value in span.attributes.values()
        )
        assert all(
            "prompt" not in key.lower() or key == "game.prompt.present"
            for key in span.attributes
        )


async def test_choose_option_valid_choice_uses_live_prompt_without_crashing():
    client = _option_client()
    platform = _option_platform(client)

    options = await platform.list_options("player1")
    result = await platform.choose_option(
        "player1",
        option_id=7,
        prompt_id=options.prompt_id,
        prompt_version=options.prompt_version,
    )

    assert result == {"player_n": "player1", "option_id": 7, "resolved": True}
    client.post.assert_awaited_once_with("player1", 7, [], [])


async def test_same_visible_prompt_with_a_new_render_id_is_a_new_prompt():
    client = _option_client(prompt="Pick one")
    platform = _option_platform(client)
    first_frame = FrameDescriptor(1, 1, (0,), 0, 0, (), "", 1, 1, 0, 1)
    next_frame = FrameDescriptor(2, 1, (0,), 0, 0, (), "", 1, 1, 0, 1)
    platform._latest_frame = first_frame
    platform._socket.wait_for_frame = AsyncMock(return_value=next_frame)
    options = await platform.list_options("player1")

    result = await platform.choose_option(
        "player1",
        option_id=7,
        prompt_id=options.prompt_id,
        prompt_version=options.prompt_version,
    )

    assert result["resolved"] is True
    client.post.assert_awaited_once_with("player1", 7, [], [])


async def test_list_options_refreshes_world_and_limits_visibility_to_addressed_seat():
    world = {
        "round_id": 1,
        "phase": "Player 1 Turn",
        "players": [],
        "area_villain": [
            {
                "id": 1,
                "card_id": "secret",
                "name": "Secret Villain",
                "is_face_up": True,
                "visible_for_players": [1],
            }
        ],
    }
    client = _option_client(world=world)
    platform = _option_platform(client, seats=("player1", "player2"))
    platform._sockets["player2"] = platform._socket
    client.get_ask.return_value["options"][0].update(
        {"all_legal_targets": [1], "target_num_range": [1, 1]}
    )

    player_one = await platform.list_options("player1")
    player_two = await platform.list_options("player2")

    assert client.get_world.await_count == 2
    assert player_one.options[0].targets[0].name == "HIDDEN"
    assert player_two.options[0].targets[0].name == "Secret Villain"


async def test_stale_prompt_with_reused_option_id_is_rejected_before_post():
    client = _option_client(prompt="First prompt")
    platform = _option_platform(client)
    old = await platform.list_options("player1")
    client.get_ask.return_value["prompt_text"] = "Second prompt"

    with pytest.raises(EnumeratedOptionError, match="stale"):
        await platform.choose_option(
            "player1",
            option_id=7,
            prompt_id=old.prompt_id,
            prompt_version=old.prompt_version,
        )

    client.post.assert_not_awaited()


async def test_choose_option_requires_prompt_identity():
    client = _option_client()
    platform = _option_platform(client)
    with pytest.raises(EnumeratedOptionError, match="prompt_id and prompt_version"):
        await platform.choose_option("player1", option_id=7)
    client.post.assert_not_awaited()


async def test_cancel_only_prompt_can_be_declined_without_an_option_id():
    client = _option_client()
    client.get_ask.return_value = {
        "prompt_text": "Cancel this effect?",
        "options": [],
        "show_cancel": True,
    }
    platform = _option_platform(client)
    options = await platform.list_options("player1")

    result = await platform.choose_option(
        "player1",
        decline=True,
        prompt_id=options.prompt_id,
        prompt_version=options.prompt_version,
    )

    assert result == {"player_n": "player1", "option_id": 0, "resolved": True}
    client.post.assert_awaited_once_with("player1", 0, [], [])


async def test_same_render_id_resolves_when_the_pending_prompt_changes():
    client = _option_client(prompt="First prompt")
    first = client.get_ask.return_value
    second = {
        "prompt_text": "Second prompt",
        "options": [{"id": 8, "name": "Next", "target_num_range": [0, 0]}],
    }
    client.get_ask = AsyncMock(return_value=first)
    platform = _option_platform(client)
    frame = FrameDescriptor(1, 1, (0,), 0, 0, (), "", 1, 1, 0, 1)
    platform._latest_frame = frame
    platform._socket.wait_for_frame = AsyncMock(return_value=frame)
    options = await platform.list_options("player1")
    client.get_ask = AsyncMock(side_effect=[first, second])

    result = await platform.choose_option(
        "player1",
        option_id=7,
        prompt_id=options.prompt_id,
        prompt_version=options.prompt_version,
    )

    assert result["resolved"] is True
    client.post.assert_awaited_once_with("player1", 7, [], [])


async def test_submission_span_records_retry_cap_rejection_before_post(monkeypatch):
    recorded = _RecordedTracer()
    monkeypatch.setattr(platform_module, "tracer", recorded)
    client = _option_client()
    platform = _option_platform(client, max_submission_attempts=1)
    options = await platform.list_options("player1")
    signature, _ = platform._pending["player1"]
    platform._attempt_guard.record(signature, 7)

    with pytest.raises(StuckPromptError):
        await platform.choose_option(
            "player1",
            option_id=7,
            prompt_id=options.prompt_id,
            prompt_version=options.prompt_version,
        )

    assert not client.post.await_args_list
    spans = [span for span in recorded.spans if span.name == "marvel_lcg.submit_option"]
    assert len(spans) == 1
    assert spans[0].attributes == {
        "game.platform": "marvel-lcg",
        "game.seat": "player1",
        "game.option.id": "7",
        "game.target.count": 0,
        "game.resource.count": 0,
        "game.outcome": "failed",
        "error.type": "StuckPromptError",
    }
    assert len(spans[0].events) == 1
    exception_event = spans[0].events[0]
    assert exception_event["name"] == "exception"
    assert exception_event["attributes"] == {
        "exception.type": "StuckPromptError",
        "exception.message": "marvel-lcg prompt remained after 1 attempts",
    }
    assert "Pick one" not in exception_event["attributes"]["exception.message"]
    assert "7" not in exception_event["attributes"]["exception.message"]


async def test_repeated_identical_post_submission_frames_reach_retry_cap():
    client = _option_client()
    platform = _option_platform(client, max_submission_attempts=1)
    repeated = FrameDescriptor(1, 1, (0,), 0, 0, (), "", 1, 1, 0, 1)
    platform._latest_frame = repeated
    platform._socket.wait_for_frame = AsyncMock(return_value=repeated)
    options = await platform.list_options("player1")

    with pytest.raises(StuckPromptError):
        await asyncio.wait_for(
            platform.choose_option(
                "player1",
                option_id=7,
                prompt_id=options.prompt_id,
                prompt_version=options.prompt_version,
            ),
            timeout=1.0,
        )

    client.post.assert_awaited_once_with("player1", 7, [], [])


async def test_marvel_rejects_typed_actions_before_transport_dispatch():
    platform = MarvelLcgPlatform("http://engine", "password", http_client=MagicMock())
    with pytest.raises(EnumeratedOptionError, match="enumerated options"):
        await platform.execute_move(MagicMock(), timeout=1)


def test_prompt_retry_identity_treats_option_ids_as_an_order_independent_set():
    client = _option_client()
    platform = _option_platform(client)
    options_a = build_options(
        {"options": [{"id": 2}, {"id": 1}]}, {}, player_n="player1", visible_seats=(0,)
    )
    options_b = build_options(
        {"options": [{"id": 1}, {"id": 2}]}, {}, player_n="player1", visible_seats=(0,)
    )
    assert platform._signature("player1", options_a) == platform._signature(
        "player1", options_b
    )


async def test_transport_degradation_is_not_terminal():
    platform = MarvelLcgPlatform("http://engine", "password", http_client=object())
    unavailable: list[dict] = []
    terminal: list[dict] = []
    platform.register_state_handlers(
        on_state_unavailable=unavailable.append, on_terminal=terminal.append
    )
    frame = FrameDescriptor(
        -1,
        1,
        (),
        0,
        0,
        (),
        "",
        1,
        1,
        0,
        1,
        transport_error="render socket reconnect exhausted",
    )
    await platform._process_frame(frame)
    assert frame.transport_degraded
    assert not frame.game_over
    assert unavailable and not terminal


async def test_degraded_transport_cannot_return_a_cached_ready_world():
    client = _option_client(world={"round_id": 1, "phase": "Player Turn"})
    platform = _option_platform(client)
    platform._degraded_seats.add(0)

    with pytest.raises(PlatformTransportError, match="transport is degraded"):
        await platform.request_state(timeout=1.0, player_n="player1")


async def test_reconnect_exhaustion_reaches_session_state_unavailable_flag():
    platform = MarvelLcgPlatform("http://engine", "password", http_client=object())
    session = GameSession(
        session_id="session-1",
        platform="marvel-lcg",
        driver=platform,
        initial_state={"ready": True},
    )
    await platform._process_frame(
        FrameDescriptor(
            -1,
            1,
            (),
            0,
            0,
            (),
            "",
            1,
            1,
            0,
            1,
            transport_error="render socket reconnect exhausted",
        )
    )

    with pytest.raises(StateUnavailableError):
        await session.get_state()


async def test_reconnect_exhaustion_publishes_degraded_frame_not_game_over():
    class BrokenSocket:
        async def recv(self):
            raise ConnectionError("socket closed")

    async def always_broken(*args, **kwargs):
        raise OSError("cannot reconnect")

    socket = MarvelLcgRenderSocket(
        "ws://engine/ws",
        seat=0,
        websocket_factory=always_broken,
        reconnect_attempts=1,
    )
    socket._socket = BrokenSocket()
    await socket._read_loop()
    frame = await socket.wait_for_frame(0.1)
    assert frame.transport_degraded
    assert not frame.game_over


async def test_socket_connect_span_has_exact_safe_attributes(monkeypatch):
    recorded = _RecordedTracer()
    monkeypatch.setattr(platform_module, "tracer", recorded)

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def open(self):
            return None

        async def close(self):
            return None

        async def wait_for_frame(self, timeout):
            del timeout
            return FrameDescriptor(1, 1, (0,), 0, 0, (), "", 1, 1, 0, 1)

    monkeypatch.setattr(platform_module, "MarvelLcgRenderSocket", FakeSocket)
    client = _option_client()
    platform = MarvelLcgPlatform(
        "http://engine", "password", http_client=client, ready_timeout=1
    )
    platform._table_created = True

    await platform.connect("room", MagicMock())

    spans = [
        span for span in recorded.spans if span.name == "marvel_lcg.socket.connect"
    ]
    assert len(spans) == 1
    assert spans[0].attributes == {
        "game.platform": "marvel-lcg",
        "game.seat.count": 1,
        "game.outcome": "connected",
    }


async def test_socket_lifecycle_telemetry_has_only_permitted_attributes(monkeypatch):
    recorded = _RecordedTracer()
    monkeypatch.setattr(frames_module, "tracer", recorded)

    class BrokenSocket:
        async def recv(self):
            raise ConnectionError("socket closed")

    async def always_broken(*args, **kwargs):
        raise OSError("cannot reconnect")

    socket = MarvelLcgRenderSocket(
        "ws://engine/ws",
        seat=0,
        websocket_factory=always_broken,
        reconnect_attempts=1,
    )
    socket._socket = BrokenSocket()
    await socket._read_loop()
    await socket.close()

    assert PERMITTED_SOCKET_TELEMETRY_ATTRIBUTE_KEYS == {
        "game.platform",
        "game.seat",
        "game.seat.count",
        "game.attempt",
        "game.outcome",
        "error.type",
    }
    names = {span.name for span in recorded.spans}
    assert {
        "marvel_lcg.socket.unexpected_close",
        "marvel_lcg.socket.reconnect",
        "marvel_lcg.socket.reconnect_exhausted",
        "marvel_lcg.socket.disconnect",
    } <= names
    for span in recorded.spans:
        assert set(span.attributes) <= PERMITTED_SOCKET_TELEMETRY_ATTRIBUTE_KEYS
        assert set(span.attributes) <= PERMITTED_DRIVER_TELEMETRY_ATTRIBUTE_KEYS
        assert all(
            not isinstance(value, (dict, list, tuple))
            for value in span.attributes.values()
        )
    exhausted = [
        span
        for span in recorded.spans
        if span.name == "marvel_lcg.socket.reconnect_exhausted"
    ]
    assert len(exhausted) == 1
    assert exhausted[0].attributes == {
        "game.platform": "marvel-lcg",
        "game.seat": 0,
        "game.attempt": 1,
        "game.outcome": "degraded",
        "error.type": "OSError",
    }


async def test_socket_announcement_span_only_wraps_handshake_sends(monkeypatch):
    recorded = _RecordedTracer()
    monkeypatch.setattr(frames_module, "tracer", recorded)
    sent: list[str] = []
    frame_payloads = [
        {
            "render_id": render_id,
            "game_id": 1,
            "ask_players": [],
            "player_id": 0,
            "total_players": 1,
        }
        for render_id in range(10)
    ]

    class SendSocket:
        def __init__(self, payloads):
            self.payloads = list(payloads)
            self.received = 0

        async def send(self, value):
            sent.append(value)

        async def recv(self):
            if self.payloads:
                self.received += 1
                return self.payloads.pop(0)
            await asyncio.Future()

        async def close(self):
            return None

    sockets: list[SendSocket] = []

    async def factory(*args, **kwargs):
        socket = SendSocket(frame_payloads if not sockets else [])
        sockets.append(socket)
        return socket

    socket = MarvelLcgRenderSocket(
        "ws://engine/ws",
        seat=0,
        websocket_factory=factory,
        reconnect_attempts=1,
    )
    await socket.open()
    while sockets[0].received < len(frame_payloads):
        await asyncio.sleep(0)
    await socket._reconnect()
    await socket.close()

    announcements = [
        span for span in recorded.spans if span.name == "marvel_lcg.socket.announce"
    ]
    assert len(sockets) == 2
    assert len(sent) == 2
    assert len(announcements) == 2
    expected_keys = {"game.platform", "game.seat", "game.outcome"}
    assert expected_keys <= PERMITTED_SOCKET_TELEMETRY_ATTRIBUTE_KEYS
    assert all(set(span.attributes) == expected_keys for span in announcements)
    assert all(span.attributes["game.outcome"] == "sent" for span in announcements)


async def test_frame_acknowledgements_are_independent_per_seat():
    client = _option_client()
    platform = _option_platform(client, seats=("player1", "player2"))
    platform._sockets["player2"] = platform._socket
    await platform._on_background_frame(
        FrameDescriptor(5, 1, (), 0, 0, (), "", 1, 1, 0, 2)
    )
    await platform._on_background_frame(
        FrameDescriptor(5, 1, (), 0, 0, (), "", 1, 1, 1, 2)
    )
    assert client.client_updated.await_args_list == [
        call("player1", 5, 1),
        call("player2", 5, 1),
    ]


def test_platform_bad_state_is_sticky_after_normalization_failure():
    platform = MarvelLcgPlatform("http://engine", "password", http_client=object())
    with pytest.raises(SessionError, match="unnormalisable"):
        platform.normalise_state([])
    with pytest.raises(SessionError, match="corrupted or unavailable"):
        platform.ensure_move_allowed()


async def test_frame_buffer_keeps_only_latest_frame():
    buffer = FrameBuffer()
    first = FrameDescriptor(1, 1, (), 0, 0, (), "", 1, 1, 0, 1)
    second = FrameDescriptor(2, 1, (), 0, 0, (), "", 2, 2, 0, 1)
    buffer.put(first)
    buffer.put(second)
    assert await buffer.get(0.1) == second


def test_prompt_guard_uses_complete_signature_not_render_id_only():
    guard = PromptAttemptGuard(max_attempts=2)
    same_render_empty = PromptSignature(4, (), "", ())
    prompt = PromptSignature(4, (0,), "Choose", ("1",))
    guard.record(same_render_empty, 1)
    guard.record(prompt, 1)
    guard.record(prompt, 2)
    with pytest.raises(StuckPromptError):
        guard.raise_if_exhausted(prompt)


def test_prompt_guard_identity_includes_render_id():
    guard = PromptAttemptGuard(max_attempts=2)
    first = PromptSignature(4, (0,), "Choose", ("1",))
    next_render = PromptSignature(5, (0,), "Choose", ("1",))

    guard.record(first, 1)
    assert guard.attempts(next_render) == 0
    guard.record(next_render, 1)
    assert guard.attempts(first) == 1
    guard.record(first, 2)
    with pytest.raises(StuckPromptError):
        guard.raise_if_exhausted(first)


async def test_marvel_platform_history_events_carry_normalized_state_and_status():
    client = _option_client(world={"round_id": 2, "phase": "Player Turn"})
    platform = _option_platform(client)
    history = _PlatformHistory()
    platform.configure_history(history, "game-1")

    options = await platform.list_options("player1")
    await platform.choose_option(
        "player1",
        option_id=7,
        prompt_id=options.prompt_id,
        prompt_version=options.prompt_version,
    )

    assert [event["event_type"] for event in history.events] == ["prompt", "move"]
    for event in history.events:
        payload = event["payload"]
        assert payload["state"]["playRound"] == 2
        assert payload["state"]["phase"] == "player"
        assert payload["status"] == "in progress"
        assert "game_over" not in payload.values()

    client.get_world.return_value = {
        "mode": "win",
        "round_id": 2,
        "phase": "Player Turn",
    }
    platform._latest_world = client.get_world.return_value
    await platform._process_frame(FrameDescriptor(-1, 1, (), 0, 0, (), "", 1, 1, 0, 1))

    terminal = history.events[-1]["payload"]
    assert terminal["status"] == "win"
    assert terminal["state"]["mode"] == "win"
    assert "game_over" not in terminal.values()


async def test_ephemeral_marvel_session_does_not_hand_driver_a_live_emitter():
    client = _option_client()
    platform = _option_platform(client)
    history = _PlatformHistory()
    session = GameSession(
        session_id="ephemeral-game",
        platform="marvel-lcg",
        driver=platform,
        history_emitter=history,
        ephemeral=True,
        initial_state={},
    )

    assert isinstance(session.history_emitter, NullHistoryEmitter)
    assert isinstance(platform.history_emitter, NullHistoryEmitter)
    await platform._process_frame(FrameDescriptor(-1, 1, (), 0, 0, (), "", 1, 1, 0, 1))
    assert history.events == []


def test_marvel_normaliser_hides_other_seat_and_preserves_play_round():
    raw = {
        "round_id": 1,
        "phase": "Player 1 Turn",
        "players": [
            {
                "resources": "3",
                "hand_cards": [
                    {
                        "id": 1,
                        "card_id": "secret-card",
                        "name": "Secret",
                        "card_type": "ally",
                        "is_face_up": True,
                        "visible_for_players": [1],
                    }
                ],
            }
        ],
        "_frame": {"current_step_id": 8, "ask_players": [0]},
    }
    state = MarvelLcgNormaliser(("player1",)).normalise(raw)
    assert state["playRound"] == 1
    assert state["phase"] == "player"
    assert state["pendingSeats"] == ["player1"]
    assert state["players"]["player1"]["resources"] == 3
    assert state["zones"]["player1Hand"] == [{"name": "HIDDEN", "stackSize": 1}]


def test_default_multiseat_normaliser_does_not_union_private_visibility():
    raw = {
        "area_villain": [
            {
                "id": 9,
                "card_id": "private-villain",
                "name": "Private Villain",
                "is_face_up": True,
                "visible_for_players": [1],
            }
        ]
    }

    default_view = MarvelLcgNormaliser(("player1", "player2")).normalise(raw)
    player_two_view = MarvelLcgNormaliser(
        ("player1", "player2"), reading_seat="player2"
    ).normalise(raw)

    assert default_view["zones"]["sharedVillain"] == [
        {"name": "HIDDEN", "stackSize": 1}
    ]
    assert player_two_view["zones"]["sharedVillain"][0]["name"] == "Private Villain"


def test_options_use_ids_and_ignore_legal_targets_when_maximum_is_zero():
    result = build_options(
        {
            "options": [
                {
                    "id": 7,
                    "name": "Play",
                    "all_legal_targets": [1],
                    "target_num_range": [0, 0],
                },
                {
                    "id": 8,
                    "name": "Play",
                    "all_legal_targets": [1],
                    "target_num_range": [1, 1],
                },
            ],
            "prompt_text": "\n--- Pick one ---",
            "show_cancel": True,
        },
        {
            "players": [],
            "area_villain": [
                {
                    "id": 1,
                    "card_id": "villain",
                    "name": "Rhino",
                    "card_type": "villain",
                    "is_face_up": True,
                    "visible_for_players": [0],
                }
            ],
        },
        player_n="player1",
        visible_seats=(0,),
    )
    assert result.prompt == "Pick one"
    assert [option.id for option in result.options] == [7, 8]
    assert result.options[0].targets == []
    assert result.options[1].targets[0].name == "Rhino"
    assert result.can_decline


async def test_http_client_fetches_version_first_handles_gzip_and_form_body():
    calls: list[tuple[str, str, str | None, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            (
                request.method,
                request.url.path,
                request.headers.get("cookie"),
                request.content,
            )
        )
        if request.url.path == "/get_version":
            return httpx.Response(
                200,
                content=b"v-test",
                headers={
                    "content-type": "image/jpeg",
                    "set-cookie": "app_version=v-test; Path=/",
                },
            )
        if request.url.path == "/get_world":
            body = gzip.compress(json.dumps({"round_id": 1}).encode())
            return httpx.Response(
                200,
                content=body,
                headers={
                    "content-type": "application/json",
                    "content-encoding": "gzip",
                },
            )
        if request.url.path == "/post":
            return httpx.Response(
                200, content=b"", headers={"content-type": "text/plain"}
            )
        raise AssertionError(request.url)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:4006", transport=httpx.MockTransport(handler)
    ) as raw:
        client = MarvelLcgHttpClient("http://127.0.0.1:4006", "password", client=raw)
        world = await client.get_world("player1")
        await client.post("player1", 7, [], [])

    assert world == {"round_id": 1}
    assert [call[1] for call in calls] == ["/get_version", "/get_world", "/post"]
    assert (
        calls[-1][2]
        and "session_token=" in calls[-1][2]
        and "app_version=v-test" in calls[-1][2]
    )
    assert json.loads(unquote(calls[-1][3].decode("ascii"))) == {
        "id": 7,
        "targets": [],
        "resources": [],
    }


async def test_new_game_and_upstream_errors_never_leak_descriptor_or_body(caplog):
    secret = "SECRET_CAMPAIGN_DESCRIPTOR"
    caplog.set_level(logging.INFO)
    caplog.set_level(logging.INFO, logger="httpx")
    telemetry._patch_logging("game-service")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/get_version":
            return httpx.Response(
                200, content=b"v-test", headers={"content-type": "text/plain"}
            )
        assert request.url.path == "/new"
        return httpx.Response(
            502,
            json={"error": secret, "descriptor": secret},
            headers={"content-type": "application/json"},
        )

    async with httpx.AsyncClient(
        base_url="http://engine", transport=httpx.MockTransport(handler)
    ) as raw:
        client = MarvelLcgHttpClient("http://engine", "password", client=raw)
        with pytest.raises(MarvelLcgHttpError) as error:
            await client.new_game(
                NewGameDescriptor(
                    campaign_json=json.dumps({"secret": secret}),
                    encounter_set_names=[],
                    hero_json=["{}"],
                )
            )

    assert secret not in str(error.value)
    logging.getLogger("httpx").info(
        "HTTP Request: POST %s", f"http://engine/new?data={quote(secret)}"
    )
    assert secret not in caplog.text


async def test_html_200_is_authentication_error_before_json_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/get_version":
            return httpx.Response(
                200, content=b"v", headers={"content-type": "image/jpeg"}
            )
        return httpx.Response(
            200, content=b"<html>login</html>", headers={"content-type": "text/html"}
        )

    async with httpx.AsyncClient(
        base_url="http://engine", transport=httpx.MockTransport(handler)
    ) as raw:
        client = MarvelLcgHttpClient("http://engine", "password", client=raw)
        with pytest.raises(MarvelLcgAuthenticationError):
            await client.list_scenarios()
