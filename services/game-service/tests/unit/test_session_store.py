from __future__ import annotations

from game_service.coordination.session_store import InMemorySessionStore


def _record(session_id: str, room_slug: str) -> dict[str, str]:
    return {
        "session_id": session_id,
        "plugin_name": "marvel-champions",
        "plugin_id": 1,
        "room_slug": room_slug,
        "created_at": "2026-06-24T00:00:00+00:00",
        "frontend_url": None,
    }


async def test_in_memory_slug_index_built_on_put():
    store = InMemorySessionStore()
    await store.put_session(_record("sid-1", "lively-fog-1234"))

    assert await store.get_session_id_by_slug("lively-fog-1234") == "sid-1"


async def test_in_memory_slug_index_unknown_slug_returns_none():
    store = InMemorySessionStore()
    await store.put_session(_record("sid-1", "lively-fog-1234"))

    assert await store.get_session_id_by_slug("does-not-exist") is None


async def test_in_memory_slug_index_removed_on_delete():
    store = InMemorySessionStore()
    await store.put_session(_record("sid-1", "lively-fog-1234"))

    await store.delete_session("sid-1")

    assert await store.get_session_id_by_slug("lively-fog-1234") is None
    assert await store.get_session("sid-1") is None


async def test_in_memory_slug_index_stale_delete_keeps_reassigned_slug():
    store = InMemorySessionStore()
    await store.put_session(_record("sid-1", "lively-fog-1234"))
    # Slug reused by a new session (old session_id still lingering).
    await store.put_session(_record("sid-2", "lively-fog-1234"))

    # Deleting the original session must not clobber the live mapping.
    await store.delete_session("sid-1")

    assert await store.get_session_id_by_slug("lively-fog-1234") == "sid-2"


async def test_in_memory_session_lock_enforces_mutual_exclusion():
    store = InMemorySessionStore()
    owner_a = "owner-a"
    owner_b = "owner-b"

    assert await store.acquire_session_lock("s1", owner_a, wait_timeout=0.1)

    acquired_b = await store.acquire_session_lock("s1", owner_b, wait_timeout=0.05)
    assert not acquired_b

    await store.release_session_lock("s1", owner_a)
    assert await store.acquire_session_lock("s1", owner_b, wait_timeout=0.1)
    await store.release_session_lock("s1", owner_b)


async def test_in_memory_session_lock_ignores_wrong_owner_release():
    store = InMemorySessionStore()

    assert await store.acquire_session_lock("s1", "owner-a", wait_timeout=0.1)
    await store.release_session_lock("s1", "owner-b")

    acquired = await store.acquire_session_lock("s1", "owner-c", wait_timeout=0.05)
    assert not acquired

    await store.release_session_lock("s1", "owner-a")
    assert await store.acquire_session_lock("s1", "owner-c", wait_timeout=0.1)
    await store.release_session_lock("s1", "owner-c")


async def test_in_memory_session_lock_allows_parallel_different_sessions():
    store = InMemorySessionStore()

    got_a = await store.acquire_session_lock("s1", "owner-a", wait_timeout=0.1)
    got_b = await store.acquire_session_lock("s2", "owner-b", wait_timeout=0.1)

    assert got_a and got_b

    await store.release_session_lock("s1", "owner-a")
    await store.release_session_lock("s2", "owner-b")
