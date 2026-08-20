"""Unit tests for how SessionManager resolves the DragnCards credential.

Pure tests — the DragnCards HTTP calls, room creation, and the Phoenix client are
all stubbed. What is under test is that one credential serves many rooms, that a
Valkey outage still produces a room, and that a credential the backend has
forgotten is evicted rather than reused for the rest of its TTL.
"""

from __future__ import annotations

import json
import logging

import pytest

from game_service.coordination.session_store import InMemorySessionStore
from game_service.dragncards import auth_cache as auth_cache_module
from game_service.dragncards.auth_cache import DragnCardsAuthCache
from game_service.logic import session_manager as session_manager_module
from game_service.logic import platform as platform_module
from game_service.logic.session_manager import SessionManager

TOKEN = "11111111-1111-4111-8111-111111111111"
SECOND_TOKEN = "22222222-2222-4222-8222-222222222222"
EMAIL = "bot@example.invalid"
PASSWORD = "not-a-real-password"
URL = "http://dragncards-backend:4000"
PLUGINS = {"marvel-champions": {"id": 1, "version": 3, "name": "Marvel Champions"}}


class FakeValkey:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.commands: list[tuple[object, ...]] = []
        self.fail_all = False

    async def execute(self, *parts: object) -> object:
        self.commands.append(parts)
        if self.fail_all:
            raise ConnectionResetError("connection reset by peer")
        command = str(parts[0]).upper()
        if command == "GET":
            return self.store.get(str(parts[1]))
        if command == "SETEX":
            self.store[str(parts[1])] = str(parts[3])
            return "OK"
        if command == "DEL":
            self.store.pop(str(parts[1]), None)
            return 1
        raise AssertionError(f"unexpected command {command}")


class FakeChannel:
    def __init__(self, room_unavailable: bool) -> None:
        self.room_unavailable = room_unavailable

    async def wait_for_state_update(self, timeout: float = 15.0):
        return {"game": {"playerInfo": {}}}

    def on(self, event, handler) -> None:  # pragma: no cover - unused here
        pass


class FakeClient:
    """Stands in for PhoenixClient; records the token each socket presented."""

    presented_tokens: list[str] = []
    refuse_tokens: set[str] = set()

    def __init__(self, ws_url: str, auth_token: str | None = None) -> None:
        self.auth_token = auth_token or ""
        FakeClient.presented_tokens.append(self.auth_token)

    async def connect(self) -> None:
        pass

    async def join(self, topic: str) -> FakeChannel:
        return FakeChannel(self.auth_token in FakeClient.refuse_tokens)

    async def leave(self, topic: str) -> None:
        pass

    async def disconnect(self) -> None:
        pass


@pytest.fixture(autouse=True)
def stub_dragncards(monkeypatch):
    """Stub the DragnCards HTTP calls, room creation, and the Phoenix client."""
    FakeClient.presented_tokens = []
    FakeClient.refuse_tokens = set()
    calls = {"token": 0, "profile": 0, "rooms": 0}
    tokens = [TOKEN, SECOND_TOKEN]

    async def fake_get_auth_token(url, email, password):
        calls["token"] += 1
        return tokens[min(calls["token"] - 1, len(tokens) - 1)]

    async def fake_get_user_id(url, token):
        calls["profile"] += 1
        return 7

    async def fake_create_room(url, token, **kwargs):
        calls["rooms"] += 1
        return {"slug": f"room-{calls['rooms']}"}

    monkeypatch.setattr(auth_cache_module, "get_auth_token", fake_get_auth_token)
    monkeypatch.setattr(auth_cache_module, "get_user_id", fake_get_user_id)
    monkeypatch.setattr(session_manager_module, "create_room", fake_create_room)
    monkeypatch.setattr(platform_module, "PhoenixClient", FakeClient)

    # Auto-seating reads state and pushes seats over the channel; neither is what
    # these tests are about, and the stub channel has no seat support.
    async def no_auto_seat(self, session, user_id):
        return None

    monkeypatch.setattr(SessionManager, "_auto_seat", no_auto_seat)
    return calls


def _manager(valkey=None, ttl: float = 900.0) -> SessionManager:
    return SessionManager(
        dragncards_http_url=URL,
        dragncards_ws_url="ws://dragncards-backend:4000/socket",
        email=EMAIL,
        password=PASSWORD,
        plugin_registry=PLUGINS,
        session_store=InMemorySessionStore(),
        auth_cache=DragnCardsAuthCache(
            URL, EMAIL, PASSWORD, valkey=valkey, ttl_seconds=ttl
        ),
    )


# ---------------------------------------------------------------------------
# One credential serves many rooms
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_sessions_authenticate_once(stub_dragncards):
    manager = _manager(FakeValkey())

    first = await manager.create_session("marvel-champions")
    second = await manager.create_session("marvel-champions")

    assert first.session_id != second.session_id
    assert stub_dragncards["rooms"] == 2
    # The saving being claimed: two rooms, one authentication and one profile read.
    assert stub_dragncards["token"] == 1
    assert stub_dragncards["profile"] == 1
    assert FakeClient.presented_tokens == [TOKEN, TOKEN]


@pytest.mark.asyncio
async def test_attach_shares_the_cached_credential(stub_dragncards):
    manager = _manager(FakeValkey())

    await manager.create_session("marvel-champions")
    await manager.attach_session("marvel-champions", "some-existing-room")

    assert stub_dragncards["token"] == 1
    assert stub_dragncards["profile"] == 1


@pytest.mark.asyncio
async def test_without_a_cache_every_session_authenticates(stub_dragncards):
    """The pre-change behaviour, which a zero TTL must restore exactly."""
    manager = _manager(FakeValkey(), ttl=0)

    await manager.create_session("marvel-champions")
    await manager.create_session("marvel-champions")

    assert stub_dragncards["token"] == 2
    assert stub_dragncards["profile"] == 2


@pytest.mark.asyncio
async def test_a_manager_built_without_an_auth_cache_still_works(stub_dragncards):
    manager = SessionManager(
        dragncards_http_url=URL,
        dragncards_ws_url="ws://dragncards-backend:4000/socket",
        email=EMAIL,
        password=PASSWORD,
        plugin_registry=PLUGINS,
        session_store=InMemorySessionStore(),
    )

    session = await manager.create_session("marvel-champions")

    assert session.room_slug == "room-1"
    assert stub_dragncards["token"] == 1


# ---------------------------------------------------------------------------
# Valkey failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_valkey_outage_still_produces_a_working_room(stub_dragncards, caplog):
    valkey = FakeValkey()
    valkey.fail_all = True
    manager = _manager(valkey)

    with caplog.at_level(logging.WARNING):
        first = await manager.create_session("marvel-champions")
        second = await manager.create_session("marvel-champions")

    assert first.room_slug == "room-1"
    assert second.room_slug == "room-2"
    # Degraded, not broken: each room authenticates live, exactly as it did before
    # the cache existed.
    assert stub_dragncards["token"] == 2
    assert valkey.commands, "the cache should still have attempted its commands"


@pytest.mark.asyncio
async def test_no_credential_appears_in_any_log_record(stub_dragncards, caplog):
    valkey = FakeValkey()
    manager = _manager(valkey)

    with caplog.at_level(logging.DEBUG):
        await manager.create_session("marvel-champions")
        await manager.create_session("marvel-champions")

    assert caplog.records, "expected session-creation logging to inspect"
    for record in caplog.records:
        rendered = record.getMessage()
        assert TOKEN not in rendered
        assert SECOND_TOKEN not in rendered
        assert PASSWORD not in rendered


# ---------------------------------------------------------------------------
# A credential the backend has forgotten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_refused_join_evicts_a_cached_credential(stub_dragncards):
    valkey = FakeValkey()
    manager = _manager(valkey)

    # First room populates the cache and joins fine.
    await manager.create_session("marvel-champions")
    key = manager._auth_cache.key
    assert json.loads(valkey.store[key])["token"] == TOKEN

    # The backend now refuses every socket presenting that token — what a recreated
    # DragnCards container looks like, since it forgets every issued credential.
    FakeClient.refuse_tokens = {TOKEN}
    await manager.create_session("marvel-champions")

    # The stale entry is gone, so the next room derives a fresh credential rather
    # than repeating the failure for the rest of the TTL.
    assert key not in valkey.store
    FakeClient.refuse_tokens = set()
    await manager.create_session("marvel-champions")
    assert FakeClient.presented_tokens[-1] == SECOND_TOKEN
    assert stub_dragncards["token"] == 2


@pytest.mark.asyncio
async def test_a_refused_join_on_a_freshly_derived_credential_is_not_evicted(
    stub_dragncards,
):
    """A refusal has causes other than the credential, e.g. no server state.

    Evicting a credential that was just minted would only re-derive the same
    thing, so the eviction is deliberately limited to a cached one.
    """
    valkey = FakeValkey()
    manager = _manager(valkey)
    FakeClient.refuse_tokens = {TOKEN}

    await manager.create_session("marvel-champions")

    key = manager._auth_cache.key
    assert json.loads(valkey.store[key])["token"] == TOKEN
    assert not any(str(c[0]).upper() == "DEL" for c in valkey.commands)


@pytest.mark.asyncio
async def test_a_refused_join_does_not_fail_session_creation(stub_dragncards):
    """Existing behaviour: a join with no state yields a session, not an error."""
    manager = _manager(FakeValkey())
    FakeClient.refuse_tokens = {TOKEN}

    session = await manager.create_session("marvel-champions")

    assert session.room_slug == "room-1"
