from __future__ import annotations

from game_service.coordination.session_store import InMemorySessionStore


async def test_in_memory_session_lock_serializes_same_session():
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

    blocked = await store.acquire_session_lock("s1", "owner-c", wait_timeout=0.05)
    assert not blocked

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
