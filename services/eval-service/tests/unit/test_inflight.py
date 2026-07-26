from __future__ import annotations

import asyncio

import pytest

from eval_service.runtime.inflight import InflightRegistry


async def _sleeper() -> None:
    await asyncio.sleep(3600)


@pytest.mark.asyncio
async def test_cancel_aborts_registered_task():
    registry = InflightRegistry()
    task = asyncio.create_task(_sleeper())
    registry.register(1, task)

    assert registry.cancel(1) is True
    with pytest.raises(asyncio.CancelledError):
        await task
    # A second cancel finds nothing running.
    assert registry.cancel(1) is False


@pytest.mark.asyncio
async def test_identity_aware_unregister_keeps_live_task():
    # A stale task finishing its ``finally`` must NOT evict the newer task a
    # force re-claim registered for the same target_id: otherwise the live task
    # becomes uncancellable.
    registry = InflightRegistry()
    stale = asyncio.create_task(_sleeper())
    fresh = asyncio.create_task(_sleeper())
    try:
        registry.register(1, stale)
        registry.register(1, fresh)  # force re-claim registered a new task

        # The stale task's finally runs and tries to unregister itself.
        registry.unregister(1, stale)

        # The fresh task is still registered and remains cancellable.
        assert registry.cancel(1) is True
        with pytest.raises(asyncio.CancelledError):
            await fresh
    finally:
        for task in (stale, fresh):
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


@pytest.mark.asyncio
async def test_unregister_without_task_drops_entry():
    registry = InflightRegistry()
    task = asyncio.create_task(_sleeper())
    registry.register(1, task)

    registry.unregister(1)  # legacy call form: unconditional drop
    assert registry.cancel(1) is False

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
