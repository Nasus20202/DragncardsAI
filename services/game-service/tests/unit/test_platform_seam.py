from __future__ import annotations

import builtins
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from game_service.api.app import create_app
from game_service.coordination.session_store import InMemorySessionStore
from game_service.api.models import SessionActionsResponse
from game_service.logic.normalisers import DragnCardsNormaliser
from game_service.logic.platform import DragnCardsPlatform, GamePlatform
from game_service.logic.room import PhoenixRoom
from game_service.logic.session import GameSession
from game_service.phoenix_client.client import Channel, PhoenixClient
from game_service.marvel_lcg.platform import MarvelLcgPlatform


def _driver() -> DragnCardsPlatform:
    client = PhoenixClient("ws://localhost:4000/socket")
    channel = Channel(topic="room:test", join_ref="1", client=client)
    return DragnCardsPlatform(client=client, channel=channel)


def test_dragncards_driver_satisfies_platform_protocol():
    assert isinstance(_driver(), GamePlatform)


def test_both_platform_drivers_satisfy_the_shared_protocol():
    marvel = MarvelLcgPlatform("http://engine", "password", http_client=object())
    assert isinstance(marvel, GamePlatform)
    assert _driver().move_surface == "typed_actions"
    assert marvel.move_surface == "enumerated_options"
    assert _driver().state_reads_are_reader_sensitive is False
    assert marvel.state_reads_are_reader_sensitive is True
    assert marvel.action_catalog()["actions"] == []


def test_game_session_created_at_defaults_to_utc_aware_datetime():
    session = GameSession(session_id="session-1", driver=_driver())

    assert session.created_at.tzinfo is not None
    assert session.created_at.utcoffset() == timezone.utc.utcoffset(None)


def test_marvel_catalog_preserves_platform_move_surface_metadata():
    marvel = MarvelLcgPlatform("http://engine", "password", http_client=object())
    response = SessionActionsResponse(
        session_id="session-1",
        plugin_name="marvel-lcg",
        actions=[],
        raw_ops=[],
        load_groups=[],
        plugin_metadata=marvel.action_catalog()["plugin_metadata"],
    )
    assert response.plugin_metadata.platform == "marvel-lcg"
    assert response.plugin_metadata.move_surface == "enumerated_options"


def test_phoenix_room_legacy_constructor_remains_available():
    client = PhoenixClient("ws://localhost:4000/socket")
    channel = Channel(topic="room:test", join_ref="1", client=client)
    room = PhoenixRoom(client, channel)
    assert room.client is client
    assert room.channel is channel


def test_phoenix_room_accepts_legacy_six_callback_registration():
    client = PhoenixClient("ws://localhost:4000/socket")
    channel = Channel(topic="room:test", join_ref="1", client=client)
    room = PhoenixRoom(client, channel)
    callbacks = [lambda payload: None for _ in range(6)]

    room.register_state_handlers(*callbacks)

    assert set(channel._handlers) == {
        "current_state",
        "state_update",
        "bad_game_state",
        "unable_to_get_state_on_join",
        "unable_to_get_state_on_request",
        "send_alert",
        "gui_update",
    }


async def test_session_platform_survives_store_round_trip():
    session = GameSession(
        session_id="session-1",
        platform="dragncards",
        plugin_name="marvel-champions",
        plugin_id=1,
        room_slug="room-1",
        created_at=datetime.now(timezone.utc),
        driver=_driver(),
    )
    store = InMemorySessionStore()
    await store.put_session(session.to_metadata())

    restored = await store.get_session("session-1")
    assert restored is not None
    assert restored["platform"] == "dragncards"


async def test_dragncards_ignored_seat_selector_keeps_cached_state():
    driver = _driver()
    initial_state = {"game": {"roundNumber": 0, "playerData": {}, "cardById": {}}}
    session = GameSession(
        session_id="session-1",
        platform="dragncards",
        plugin_name="marvel-champions",
        driver=driver,
        initial_state=initial_state,
    )

    assert await session.get_state(player_n="player2") is initial_state


def test_dragncards_normaliser_adds_neutral_phase_and_play_round():
    result = DragnCardsNormaliser().normalise(
        {"game": {"roundNumber": 0, "stepId": "1.1", "cardById": {}}},
        plugin_name="marvel-champions",
    )

    assert result["playRound"] == 1
    assert "roundNumber" not in result
    assert result["phase"] == "player"
    assert result["phaseLabel"] == "Player Turn"
    # Pending seats are platform-specific and absent for DragnCards.
    assert "pendingSeats" not in result


def test_dragncards_beginning_of_round_is_passive_play_round_one():
    result = DragnCardsNormaliser().normalise(
        {"game": {"roundNumber": 0, "stepId": "0.0", "cardById": {}}},
        plugin_name="marvel-champions",
    )

    assert result["playRound"] == 1
    assert result["phase"] == "passive"
    assert result["phaseLabel"] == "Beginning of Round"


def test_dragncards_player_phase_is_the_only_playable_phase():
    result = DragnCardsNormaliser().normalise(
        {"game": {"roundNumber": 0, "stepId": "1.1", "cardById": {}}},
        plugin_name="marvel-champions",
    )

    assert result["playRound"] == 1
    assert result["phase"] == "player"


def test_openapi_build_does_not_require_plugin_json(tmp_path):
    env = os.environ.copy()
    env["DRAGNCARDS_MC_PLUGIN_JSON_DIR"] = str(tmp_path / "missing-plugin")
    service_root = Path(__file__).parents[2]
    env["PYTHONPATH"] = os.pathsep.join(
        [str(service_root / "src"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from game_service.api.app import create_app; schema = create_app().openapi(); assert schema['paths']; assert 'standard2Player' in schema['components']['schemas']['SetPlayerCountRequest']['properties']['layout_id']['anyOf'][0]['enum']",
        ],
        env=env,
        cwd=service_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_openapi_generation_never_reads_plugin_files(monkeypatch):
    from game_service.catalog.providers.marvel_champions import plugin_metadata

    real_open = builtins.open

    def fail_plugin_open(filename, *args, **kwargs):
        if "dragncards-mc-plugin" in str(filename):
            raise AssertionError(f"OpenAPI attempted filesystem read: {filename}")
        return real_open(filename, *args, **kwargs)

    def fail_plugin_read(filename):
        raise AssertionError(f"OpenAPI attempted to read plugin metadata: {filename}")

    monkeypatch.setattr(builtins, "open", fail_plugin_open)
    monkeypatch.setattr(plugin_metadata, "_load_plugin_json", fail_plugin_read)

    schema = create_app().openapi()
    layout_schema = schema["components"]["schemas"]["SetPlayerCountRequest"][
        "properties"
    ]["layout_id"]
    assert "standard2Player" in layout_schema["anyOf"][0]["enum"]
