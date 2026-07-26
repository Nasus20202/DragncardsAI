from __future__ import annotations

from datetime import timedelta

import pytest

from history_service.config import Settings
from history_service.runtime.snapshots import SnapshotService

from .conftest import make_envelope


class FakeGameService:
    def __init__(self):
        self.calls = 0

    async def get_snapshot(self, game_id: str) -> dict:
        self.calls += 1
        return {"schema_version": 1, "plugin_name": "marvel-champions", "game": {}}


@pytest.mark.asyncio
async def test_snapshot_taken_after_event_count(repository):
    settings = Settings(snapshot_every_n_events=3, snapshot_max_interval_seconds=999)
    game = FakeGameService()
    service = SnapshotService(
        settings=settings, repository=repository, game_service=game
    )

    for offset in range(3):
        result = await repository.commit_event(
            make_envelope("g1", producer_offset=offset)
        )
        snap = await service.maybe_snapshot("g1", result.event.seq)

    assert game.calls == 1
    snapshots = await repository.list_snapshots("g1")
    assert len(snapshots) == 1 and snapshots[0].snapshot_at_seq == 3


@pytest.mark.asyncio
async def test_no_snapshot_before_threshold(repository):
    settings = Settings(snapshot_every_n_events=5, snapshot_max_interval_seconds=999)
    game = FakeGameService()
    service = SnapshotService(
        settings=settings, repository=repository, game_service=game
    )

    for offset in range(4):
        result = await repository.commit_event(
            make_envelope("g1", producer_offset=offset)
        )
        await service.maybe_snapshot("g1", result.event.seq)

    assert game.calls == 0
    assert await repository.list_snapshots("g1") == []


@pytest.mark.asyncio
async def test_snapshot_taken_after_interval(repository):
    settings = Settings(snapshot_every_n_events=100, snapshot_max_interval_seconds=60)
    game = FakeGameService()
    service = SnapshotService(
        settings=settings, repository=repository, game_service=game
    )

    # Seed a first snapshot, then backdate it so the interval has "elapsed".
    for offset in range(2):
        await repository.commit_event(make_envelope("g1", producer_offset=offset))
    await service.take_snapshot("g1", 2)
    # Patch list_snapshots to return a backdated copy for the cadence check.
    original = repository.list_snapshots

    async def patched(game_id):
        items = await original(game_id)
        for item in items:
            item.created_at = item.created_at - timedelta(seconds=120)
        return items

    repository.list_snapshots = patched  # type: ignore[assignment]
    try:
        await repository.commit_event(make_envelope("g1", producer_offset=2))
        due = await service.is_snapshot_due("g1", 3)
        assert due is True
    finally:
        repository.list_snapshots = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_snapshot_stored_in_documented_format(repository):
    settings = Settings(snapshot_every_n_events=1, snapshot_max_interval_seconds=999)
    game = FakeGameService()
    service = SnapshotService(
        settings=settings, repository=repository, game_service=game
    )
    result = await repository.commit_event(make_envelope("g1", producer_offset=0))
    stored = await service.maybe_snapshot("g1", result.event.seq)
    assert stored is not None
    assert stored.snapshot["schema_version"] == 1
    assert stored.snapshot["plugin_name"] == "marvel-champions"
    assert "game" in stored.snapshot
