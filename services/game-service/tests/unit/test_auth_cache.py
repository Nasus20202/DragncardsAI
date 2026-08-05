"""Unit tests for the Valkey-backed DragnCards credential cache.

Pure tests — no network, no Valkey. The DragnCards HTTP calls are patched and the
Valkey connection is a stub, so what is under test is the cache's own behaviour:
that a hit avoids the round trips, that every way Valkey can fail degrades to a
live authentication, and that the token never escapes into a log record.
"""

from __future__ import annotations

import json
import logging

import pytest

from game_service.dragncards import auth_cache as auth_cache_module
from game_service.dragncards.auth_cache import (
    DEFAULT_TTL_SECONDS,
    DRAGNCARDS_TOKEN_LIFETIME_SECONDS,
    KEY_PREFIX,
    DragnCardsAuthCache,
    DragnCardsIdentity,
)

TOKEN = "3f2a5c11-0000-4aaa-bbbb-1234567890ab"
OTHER_TOKEN = "9e8d7c66-1111-4ccc-dddd-0987654321ba"
EMAIL = "bot@example.invalid"
PASSWORD = "not-a-real-password"
URL = "http://dragncards-backend:4000"


class FakeValkey:
    """Records commands and replays a scripted store."""

    def __init__(self, store: dict[str, str] | None = None) -> None:
        self.store: dict[str, str] = dict(store or {})
        self.commands: list[tuple[object, ...]] = []
        self.fail_on: set[str] = set()

    async def execute(self, *parts: object) -> object:
        self.commands.append(parts)
        command = str(parts[0]).upper()
        if command in self.fail_on:
            raise ConnectionResetError("connection reset by peer")
        if command == "GET":
            return self.store.get(str(parts[1]))
        if command == "SETEX":
            self.store[str(parts[1])] = str(parts[3])
            return "OK"
        if command == "DEL":
            self.store.pop(str(parts[1]), None)
            return 1
        raise AssertionError(f"unexpected command {command}")

    def commands_named(self, name: str) -> list[tuple[object, ...]]:
        return [c for c in self.commands if str(c[0]).upper() == name]


@pytest.fixture
def live_auth(monkeypatch):
    """Patch the two DragnCards calls and count how often each is made."""
    calls = {"token": 0, "profile": 0}
    tokens = [TOKEN, OTHER_TOKEN]

    async def fake_get_auth_token(url, email, password):
        calls["token"] += 1
        return tokens[min(calls["token"] - 1, len(tokens) - 1)]

    async def fake_get_user_id(url, token):
        calls["profile"] += 1
        return 7

    monkeypatch.setattr(auth_cache_module, "get_auth_token", fake_get_auth_token)
    monkeypatch.setattr(auth_cache_module, "get_user_id", fake_get_user_id)
    return calls


def _cache(valkey=None, ttl: float = DEFAULT_TTL_SECONDS) -> DragnCardsAuthCache:
    return DragnCardsAuthCache(URL, EMAIL, PASSWORD, valkey=valkey, ttl_seconds=ttl)


# ---------------------------------------------------------------------------
# TTL is chosen against the token's real lifetime
# ---------------------------------------------------------------------------


def test_default_ttl_is_shorter_than_the_token_lifetime():
    # The whole safety argument for caching a credential is that an entry cannot
    # outlive the credential in it. Pin the relationship, not just the number, so
    # raising one without the other fails here.
    assert DEFAULT_TTL_SECONDS < DRAGNCARDS_TOKEN_LIFETIME_SECONDS
    assert DEFAULT_TTL_SECONDS <= DRAGNCARDS_TOKEN_LIFETIME_SECONDS / 2


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def test_key_is_namespaced_and_carries_no_account_address():
    cache = _cache()
    assert cache.key.startswith(KEY_PREFIX)
    assert EMAIL not in cache.key
    assert "@" not in cache.key.removeprefix(KEY_PREFIX)


def test_key_differs_per_backend_and_per_account():
    base = _cache().key
    other_backend = DragnCardsAuthCache(
        "http://other-backend:4000", EMAIL, PASSWORD
    ).key
    other_account = DragnCardsAuthCache(URL, "other.bot@example.invalid", PASSWORD).key
    assert base != other_backend
    assert base != other_account
    assert other_backend != other_account


# ---------------------------------------------------------------------------
# Hit / miss
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_hit_avoids_both_dragncards_round_trips(live_auth):
    cache = _cache(FakeValkey())
    valkey = FakeValkey({cache.key: json.dumps({"token": TOKEN, "user_id": 7})})
    cache = _cache(valkey)

    identity = await cache.resolve()

    assert identity == DragnCardsIdentity(token=TOKEN, user_id=7, cached=True)
    assert live_auth == {"token": 0, "profile": 0}
    assert valkey.commands_named("SETEX") == []


@pytest.mark.asyncio
async def test_cache_miss_authenticates_and_stores_with_the_configured_ttl(live_auth):
    valkey = FakeValkey()
    cache = _cache(valkey, ttl=123.4)

    identity = await cache.resolve()

    assert identity == DragnCardsIdentity(token=TOKEN, user_id=7, cached=False)
    assert live_auth == {"token": 1, "profile": 1}
    (setex,) = valkey.commands_named("SETEX")
    assert setex[1] == cache.key
    assert setex[2] == "123"  # rounded to whole seconds for SETEX
    assert json.loads(str(setex[3])) == {"token": TOKEN, "user_id": 7}


@pytest.mark.asyncio
async def test_a_second_resolve_reuses_the_entry_the_first_one_wrote(live_auth):
    valkey = FakeValkey()
    cache = _cache(valkey)

    first = await cache.resolve()
    second = await cache.resolve()

    assert live_auth == {"token": 1, "profile": 1}
    assert second.token == first.token
    assert second.user_id == first.user_id
    assert second.cached is True


@pytest.mark.asyncio
async def test_a_positive_ttl_never_rounds_down_to_disabled(live_auth):
    valkey = FakeValkey()
    cache = _cache(valkey, ttl=0.2)

    await cache.resolve()

    (setex,) = valkey.commands_named("SETEX")
    assert setex[2] == "1"


# ---------------------------------------------------------------------------
# Disabled cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_zero_ttl_performs_no_valkey_command_at_all(live_auth):
    valkey = FakeValkey()
    cache = _cache(valkey, ttl=0)

    identity = await cache.resolve()

    assert cache.enabled is False
    assert identity.token == TOKEN
    assert valkey.commands == []
    assert live_auth == {"token": 1, "profile": 1}


@pytest.mark.asyncio
async def test_no_valkey_connection_authenticates_live(live_auth):
    cache = _cache(None)

    identity = await cache.resolve()

    assert cache.enabled is False
    assert identity.token == TOKEN
    assert live_auth == {"token": 1, "profile": 1}


# ---------------------------------------------------------------------------
# Failure degrades to live authentication
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_read_that_raises_still_yields_a_working_credential(live_auth, caplog):
    valkey = FakeValkey()
    valkey.fail_on = {"GET"}
    cache = _cache(valkey)

    with caplog.at_level(logging.WARNING):
        identity = await cache.resolve()

    assert identity == DragnCardsIdentity(token=TOKEN, user_id=7, cached=False)
    assert live_auth == {"token": 1, "profile": 1}
    assert any("GET failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_a_write_that_raises_still_yields_a_working_credential(live_auth, caplog):
    valkey = FakeValkey()
    valkey.fail_on = {"SETEX"}
    cache = _cache(valkey)

    with caplog.at_level(logging.WARNING):
        identity = await cache.resolve()

    assert identity == DragnCardsIdentity(token=TOKEN, user_id=7, cached=False)
    assert live_auth == {"token": 1, "profile": 1}
    assert any("SETEX failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_every_valkey_command_failing_still_yields_a_credential(live_auth):
    """A wholly unreachable Valkey — the outage case — must not break a room."""
    valkey = FakeValkey()
    valkey.fail_on = {"GET", "SETEX", "DEL"}
    cache = _cache(valkey)

    identity = await cache.resolve()

    assert identity.token == TOKEN
    await cache.invalidate()  # must not raise either


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stored",
    [
        "not json at all",
        json.dumps({"user_id": 7}),
        json.dumps({"token": "", "user_id": 7}),
        json.dumps({"token": TOKEN, "user_id": "not a number"}),
        json.dumps(["token", TOKEN]),
    ],
)
async def test_an_unusable_stored_value_is_treated_as_a_miss(live_auth, stored):
    cache = _cache(FakeValkey())
    valkey = FakeValkey({cache.key: stored})
    cache = _cache(valkey)

    identity = await cache.resolve()

    assert identity == DragnCardsIdentity(token=TOKEN, user_id=7, cached=False)
    assert live_auth == {"token": 1, "profile": 1}


# ---------------------------------------------------------------------------
# Invalidation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalidate_deletes_the_entry_so_the_next_resolve_re_derives(live_auth):
    valkey = FakeValkey()
    cache = _cache(valkey)

    first = await cache.resolve()
    await cache.invalidate()
    second = await cache.resolve()

    assert valkey.commands_named("DEL")[0][1] == cache.key
    assert first.token == TOKEN
    assert second.token == OTHER_TOKEN
    assert live_auth == {"token": 2, "profile": 2}


@pytest.mark.asyncio
async def test_refresh_ignores_a_stored_entry(live_auth):
    cache = _cache(FakeValkey())
    valkey = FakeValkey({cache.key: json.dumps({"token": TOKEN, "user_id": 7})})
    cache = _cache(valkey)

    identity = await cache.refresh()

    assert identity.cached is False
    assert live_auth == {"token": 1, "profile": 1}


# ---------------------------------------------------------------------------
# The token must not leak
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_log_record_on_any_path_contains_the_token(live_auth, caplog):
    """Every diagnostic the cache emits, across hit, miss and failure."""
    cache = _cache(FakeValkey())
    valkey = FakeValkey({cache.key: "not json at all"})
    valkey.fail_on = {"GET", "SETEX", "DEL"}
    cache = _cache(valkey)

    with caplog.at_level(logging.DEBUG):
        await cache.resolve()
        await cache.invalidate()
        valkey.fail_on = set()
        valkey.store[cache.key] = json.dumps({"token": TOKEN, "user_id": 7})
        await cache.resolve()
        await cache.refresh()

    assert caplog.records, "expected at least one diagnostic to inspect"
    for record in caplog.records:
        rendered = record.getMessage()
        assert TOKEN not in rendered
        assert OTHER_TOKEN not in rendered
        assert PASSWORD not in rendered


# ---------------------------------------------------------------------------
# The span the credential commands are traced under
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_span_attribute_carries_a_command_argument(monkeypatch):
    """DRA-36: the cache stores a credential, so tracing must stay argument-free.

    The session-store RESP client is what traces these commands, and it records
    only ``parts[0]`` as ``db.operation.name``. Caching a credential makes that a
    security property rather than a stylistic one — a ``SETEX`` whose arguments
    reached a span attribute would publish the token to the trace backend — so it
    is asserted against the real connection rather than assumed.
    """
    from game_service.coordination import session_store

    recorded: list[dict[str, object]] = []

    class FakeSpan:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class FakeTracer:
        def start_as_current_span(self, name, attributes=None):
            recorded.append(dict(attributes or {}))
            return FakeSpan()

    async def fake_open_connection(host, port):
        raise ConnectionRefusedError("no Valkey in a unit test")

    monkeypatch.setattr(session_store, "tracer", FakeTracer())
    monkeypatch.setattr(session_store.asyncio, "open_connection", fake_open_connection)

    connection = session_store._RespConnection("localhost", 6379)
    cache = _cache(connection)
    # Both commands the cache issues, exercised through the real client. Each one
    # fails at the socket, which the cache reports as a miss — the span is opened
    # before that, which is what is under test.
    await cache._write(TOKEN, 7)
    await cache._read()

    assert recorded, "expected the RESP client to open a span per command"
    for attributes in recorded:
        assert set(attributes) == {
            "db.system",
            "db.operation.name",
            "server.address",
            "server.port",
        }
        rendered = " ".join(str(value) for value in attributes.values())
        assert TOKEN not in rendered
        assert cache.key not in rendered
