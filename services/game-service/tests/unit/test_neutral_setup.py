from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest
from fastmcp import Client

from game_service.api.app import create_app
from game_service.coordination.session_store import (
    InMemorySessionStore,
    ValkeySessionStore,
)
from game_service.logic.exceptions import SessionError
from game_service.logic.platform import HeroDeckSelection, MarvelLcgCreateSpec
from game_service.logic.session import GameSession
from game_service.logic.session_manager import SessionManager
from game_service.marvel_lcg.client import MarvelLcgError
from game_service.marvel_lcg.platform import MarvelLcgPlatform
from game_service.mcp.server import create_mcp_server


def _catalog_client() -> MagicMock:
    client = MagicMock()
    client.list_scenarios = AsyncMock(return_value=["scenario-a.json"])
    client.list_starter_deck = AsyncMock(return_value=["hero-a.json", "hero-b.json"])
    client.get_scenario_json = AsyncMock(return_value="{}")
    client.get_hero_json = AsyncMock(return_value="{}")
    client.new_game = AsyncMock(return_value={"result": "New game created"})
    return client


class LeaseProbeStore(InMemorySessionStore):
    supports_distributed_leases = True

    def __init__(self) -> None:
        super().__init__()
        self._leases: dict[str, tuple[str, str]] = {}
        self.claims: list[tuple[str, str, str]] = []
        self.releases: list[tuple[str, str]] = []
        self.renew_calls = 0
        self.owned_calls = 0

    async def acquire_marvel_lease(
        self, endpoint: str, session_id: str, owner_token: str, *, lease_ttl: float
    ) -> bool:
        del lease_ttl
        if endpoint in self._leases:
            return False
        self._leases[endpoint] = (session_id, owner_token)
        self.claims.append((endpoint, session_id, owner_token))
        return True

    async def renew_marvel_lease(
        self, endpoint: str, owner_token: str, *, lease_ttl: float
    ) -> bool:
        del lease_ttl
        self.renew_calls += 1
        return endpoint in self._leases and self._leases[endpoint][1] == owner_token

    async def marvel_lease_owned(self, endpoint: str, owner_token: str) -> bool:
        self.owned_calls += 1
        return endpoint in self._leases and self._leases[endpoint][1] == owner_token

    async def release_marvel_lease(self, endpoint: str, owner_token: str) -> None:
        self.releases.append((endpoint, owner_token))
        if endpoint in self._leases and self._leases[endpoint][1] == owner_token:
            del self._leases[endpoint]


def _marvel_spec(platform: MarvelLcgPlatform) -> MarvelLcgCreateSpec:
    return MarvelLcgCreateSpec(
        platform="marvel-lcg",
        scenario_id=platform._catalog_id("scenario", "scenario-a.json"),
        hero_decks=(
            HeroDeckSelection(
                "player1", platform._catalog_id("hero-deck", "hero-a.json")
            ),
        ),
    )


def _delayed_marvel_platform(
    *, create_delay: float = 0.0, connect_delay: float = 0.0, fail_create: bool = False
) -> MarvelLcgPlatform:
    platform = MarvelLcgPlatform(
        "http://engine", "password", http_client=_catalog_client()
    )
    platform.new_session = lambda: platform
    platform.authenticate = AsyncMock(return_value=MagicMock(user_id=None))
    platform.resolve_create_spec = AsyncMock(side_effect=lambda spec: spec)

    async def create_table(identity, spec):
        del identity, spec
        await asyncio.sleep(create_delay)
        if fail_create:
            raise SessionError("delayed create failed")
        return {"slug": "marvel-room"}

    async def connect(room_slug, identity):
        del room_slug, identity
        await asyncio.sleep(connect_delay)
        return {"world": {}}

    platform.create_table = create_table
    platform.connect = connect
    platform.teardown = AsyncMock()
    return platform


async def test_marvel_catalog_ids_are_opaque_and_creation_preserves_deck_order():
    client = _catalog_client()
    platform = MarvelLcgPlatform("http://engine", "password", http_client=client)

    catalog = await platform.setup_catalog()
    scenario_id = catalog["scenarios"][0]["id"]
    deck_a = catalog["hero_decks"][0]["id"]
    deck_b = catalog["hero_decks"][1]["id"]
    assert scenario_id != "scenario-a.json"
    assert deck_a != "hero-a.json"

    await platform.create_table(
        MagicMock(),
        MarvelLcgCreateSpec(
            platform="marvel-lcg",
            scenario_id=scenario_id,
            hero_decks=(
                HeroDeckSelection("player1", deck_b),
                HeroDeckSelection("player2", deck_a),
            ),
        ),
    )

    client.get_scenario_json.assert_awaited_with("scenario-a.json")
    assert client.get_hero_json.await_args_list[-2:] == [
        call("hero-b.json"),
        call("hero-a.json"),
    ]
    descriptor = client.new_game.await_args.args[0]
    assert descriptor.hero_json == ["{}", "{}"]
    assert platform.held_seats == ("player1", "player2")
    metadata = platform.session_metadata(
        plugin_name="", plugin_id=None, plugin_version=None
    )
    assert [item["hero_deck_id"] for item in metadata["setup"]["hero_decks"]] == [
        deck_b,
        deck_a,
    ]


async def test_marvel_catalog_id_survives_leading_relative_path_change():
    client = _catalog_client()
    client.list_scenarios = AsyncMock(
        side_effect=[
            ["./data/scenarios/rhino.json"],
            ["data/scenarios/rhino.json"],
        ]
    )
    client.list_starter_deck = AsyncMock(
        side_effect=[
            ["./deck/starter/spider_man.json"],
            ["deck/starter/spider_man.json"],
        ]
    )
    client.get_scenario_json = AsyncMock(return_value='{"scenario":true}')
    client.get_hero_json = AsyncMock(return_value='{"hero":"spider-man"}')

    platform = MarvelLcgPlatform("http://engine", "password", http_client=client)
    catalog = await platform.setup_catalog()
    spider_id = catalog["hero_decks"][0]["id"]

    assert spider_id == "hero-deck:377e837cafe661012d4e09eb"
    await platform.create_table(
        MagicMock(),
        MarvelLcgCreateSpec(
            platform="marvel-lcg",
            scenario_id=catalog["scenarios"][0]["id"],
            hero_decks=(HeroDeckSelection("player1", spider_id),),
        ),
    )

    client.get_scenario_json.assert_awaited_once_with("data/scenarios/rhino.json")
    client.get_hero_json.assert_awaited_once_with("deck/starter/spider_man.json")
    assert client.new_game.await_args.args[0].hero_json == ['{"hero":"spider-man"}']


async def test_marvel_catalog_aliases_do_not_accept_raw_paths():
    client = _catalog_client()
    platform = MarvelLcgPlatform("http://engine", "password", http_client=client)
    scenario_id = platform._catalog_id("scenario", "scenario-a.json")

    with pytest.raises(SessionError, match="Unknown marvel-lcg hero_deck_id"):
        await platform.resolve_create_spec(
            MarvelLcgCreateSpec(
                platform="marvel-lcg",
                scenario_id=scenario_id,
                hero_decks=(
                    HeroDeckSelection("player1", "./deck/starter/spider_man.json"),
                ),
            )
        )

    client.get_scenario_json.assert_not_awaited()
    client.get_hero_json.assert_not_awaited()
    client.new_game.assert_not_awaited()


async def test_invalid_marvel_setup_fails_before_table_creation():
    client = _catalog_client()
    platform = MarvelLcgPlatform("http://engine", "password", http_client=client)

    with pytest.raises(SessionError, match="Unknown marvel-lcg scenario_id"):
        await platform.create_table(
            MagicMock(),
            MarvelLcgCreateSpec(
                platform="marvel-lcg",
                scenario_id="scenario:not-in-catalog",
                hero_decks=(HeroDeckSelection("player1", "hero-deck:not-in-catalog"),),
            ),
        )

    client.get_scenario_json.assert_not_awaited()
    client.new_game.assert_not_awaited()


@pytest.mark.parametrize(
    "seats",
    [
        ("player2", "player1"),
        ("player1", "player3"),
    ],
)
async def test_marvel_driver_rejects_reverse_or_gapped_rosters(seats):
    client = _catalog_client()
    platform = MarvelLcgPlatform("http://engine", "password", http_client=client)
    decks = tuple(
        HeroDeckSelection(seat, platform._catalog_id("hero-deck", path))
        for seat, path in zip(seats, ("hero-a.json", "hero-b.json"))
    )

    with pytest.raises(SessionError, match="ordered contiguous prefix"):
        await platform.resolve_create_spec(
            MarvelLcgCreateSpec(
                platform="marvel-lcg",
                scenario_id=platform._catalog_id("scenario", "scenario-a.json"),
                hero_decks=decks,
            )
        )


async def test_marvel_creation_refuses_in_memory_store_instead_of_using_a_local_lock():
    client = _catalog_client()
    platform = MarvelLcgPlatform("http://engine", "password", http_client=client)
    manager = SessionManager(
        platform_registry={"marvel-lcg": platform},
        session_store=InMemorySessionStore(),
    )

    with pytest.raises(SessionError, match="Valkey-backed session store"):
        await manager.create_session(platform="marvel-lcg")
    client.new_game.assert_not_awaited()


async def test_marvel_lease_renews_during_delayed_creation_and_connection():
    platform = _delayed_marvel_platform(create_delay=0.13, connect_delay=0.13)
    store = LeaseProbeStore()
    manager = SessionManager(
        platform_registry={"marvel-lcg": platform},
        session_store=store,
        marvel_lease_ttl_seconds=0.12,
    )

    session = await manager.create_session(
        platform="marvel-lcg", setup=_marvel_spec(platform)
    )

    assert store.renew_calls >= 2
    assert store.owned_calls >= 1
    assert session.degraded is False
    await manager.delete_session(session.session_id)


async def test_marvel_creation_failure_releases_pre_registered_exact_lease():
    platform = _delayed_marvel_platform(create_delay=0.22, fail_create=True)
    store = LeaseProbeStore()
    manager = SessionManager(
        platform_registry={"marvel-lcg": platform},
        session_store=store,
        marvel_lease_ttl_seconds=0.12,
    )

    with pytest.raises(SessionError, match="delayed create failed"):
        await manager.create_session(
            platform="marvel-lcg", setup=_marvel_spec(platform)
        )

    assert store.renew_calls >= 1
    assert len(store.claims) == 1
    assert store.releases == [(store.claims[0][0], store.claims[0][2])]
    assert manager._marvel_leases == {}
    assert manager._marvel_lease_tasks == {}


async def test_marvel_close_room_is_rejected_without_closing_or_releasing():
    platform = MarvelLcgPlatform(
        "http://engine", "password", http_client=_catalog_client()
    )
    platform.push_event = AsyncMock()
    transport = MagicMock()
    platform._sockets["player1"] = transport
    on_close = AsyncMock()
    session = GameSession(
        session_id="marvel-session",
        room_slug="marvel-room",
        driver=platform,
        on_close=on_close,
    )

    with pytest.raises(SessionError, match="does not support close_room"):
        await session.close_room()

    platform.push_event.assert_not_awaited()
    on_close.assert_not_awaited()
    transport.close.assert_not_called()


async def test_valkey_marvel_lease_release_compares_the_stored_lease_value():
    store = ValkeySessionStore("valkey://localhost:6379")
    store._conn = MagicMock()
    store._conn.execute = AsyncMock(
        side_effect=[
            '{"session_id":"session-1","owner_token":"owner-1"}',
            1,
        ]
    )

    await store.release_marvel_lease("http://engine", "owner-1")

    assert store._conn.execute.await_args_list[0] == call(
        "GET", store._marvel_lease_key("http://engine")
    )
    assert store._conn.execute.await_args_list[1].args[-1] == (
        '{"session_id":"session-1","owner_token":"owner-1"}'
    )


async def test_valkey_marvel_lease_release_does_not_delete_another_owner_lease():
    store = ValkeySessionStore("valkey://localhost:6379")
    store._conn = MagicMock()
    store._conn.execute = AsyncMock(
        return_value='{"session_id":"session-2","owner_token":"owner-2"}'
    )

    await store.release_marvel_lease("http://engine", "owner-1")

    store._conn.execute.assert_awaited_once_with(
        "GET", store._marvel_lease_key("http://engine")
    )


async def test_neutral_catalog_is_http_and_generated_mcp_surface():
    manager = MagicMock()
    manager._platform_registry = {"marvel-lcg": MagicMock()}
    manager.list_setup_catalog = AsyncMock(
        return_value={
            "platform": "dragncards",
            "move_surface": "typed_actions",
            "plugins": [
                {
                    "id": "marvel-champions",
                    "name": "marvel-champions",
                    "display_name": "Marvel Champions",
                }
            ],
            "scenarios": [],
            "hero_decks": [],
        }
    )
    app = create_app(session_manager=manager)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/games/setup-catalog", params={"platform": "dragncards"}
        )
    assert response.status_code == 200
    assert response.json()["move_surface"] == "typed_actions"

    mcp = create_mcp_server(session_manager=manager, fastapi_app=app)
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(tool for tool in tools if tool.name == "list_game_setup_catalog")
    assert tool.inputSchema["additionalProperties"] is False
    assert "platform" in tool.inputSchema["properties"]
    create_tool = next(tool for tool in tools if tool.name == "create_game")
    assert "setup" in create_tool.inputSchema["properties"]
    assert create_tool.inputSchema["additionalProperties"] is False
    choose_tool = next(tool for tool in tools if tool.name == "choose_game_option")
    assert {"prompt_id", "prompt_version"} <= set(choose_tool.inputSchema["required"])
    assert "player" not in choose_tool.inputSchema["properties"]

    session_setup = app.openapi()["components"]["schemas"]["SessionMetadata"][
        "properties"
    ]["setup"]
    resolved_setup_schema = session_setup["anyOf"][0]
    assert {
        item["$ref"].rsplit("/", 1)[-1] for item in resolved_setup_schema["oneOf"]
    } == {
        "ResolvedDragnCardsSetup",
        "ResolvedMarvelLcgSetup",
    }


async def test_create_and_option_contracts_reject_wrong_discriminators():
    app = create_app(session_manager=MagicMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        mismatch = await client.post(
            "/games",
            json={
                "platform": "dragncards",
                "setup": {
                    "platform": "marvel-lcg",
                    "scenario_id": "scenario:x",
                    "hero_decks": [{"seat": "player1", "hero_deck_id": "hero-deck:x"}],
                },
            },
        )
        stale_option_arg = await client.post(
            "/games/session/options/choose",
            json={
                "player": "player1",
                "option_id": 1,
                "prompt_id": "prompt",
                "prompt_version": 1,
            },
        )
        reverse_roster = await client.post(
            "/games",
            json={
                "platform": "marvel-lcg",
                "setup": {
                    "platform": "marvel-lcg",
                    "scenario_id": "scenario:x",
                    "hero_decks": [
                        {"seat": "player2", "hero_deck_id": "hero-deck:x"},
                        {"seat": "player1", "hero_deck_id": "hero-deck:y"},
                    ],
                },
            },
        )
        gapped_roster = await client.post(
            "/games",
            json={
                "platform": "marvel-lcg",
                "setup": {
                    "platform": "marvel-lcg",
                    "scenario_id": "scenario:x",
                    "hero_decks": [
                        {"seat": "player1", "hero_deck_id": "hero-deck:x"},
                        {"seat": "player3", "hero_deck_id": "hero-deck:y"},
                    ],
                },
            },
        )
    assert mismatch.status_code == 422
    assert stale_option_arg.status_code == 422
    assert reverse_roster.status_code == 422
    assert gapped_roster.status_code == 422


async def test_unavailable_marvel_backend_is_readiness_oriented_503():
    manager = MagicMock()
    manager.list_setup_catalog = AsyncMock(
        side_effect=MarvelLcgError("marvel-lcg request failed")
    )
    app = create_app(session_manager=manager)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/games/setup-catalog", params={"platform": "marvel-lcg"}
        )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
