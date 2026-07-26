from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.postgres


async def _seed_request(repository, request_id="r1", game_id="g1"):
    await repository.create_request(
        request_id=request_id,
        game_id=game_id,
        scope="move",
        selection={"seqs": [2]},
        force=False,
    )


@pytest.mark.asyncio
async def test_target_evaluated_at_most_once(postgres_repository):
    await _seed_request(postgres_repository)
    first = await postgres_repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
    )
    second = await postgres_repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
    )
    assert first.claimed is True
    assert second.claimed is False


@pytest.mark.asyncio
async def test_concurrent_claims_resolve_to_one(postgres_repository):
    await _seed_request(postgres_repository)

    async def claim():
        return await postgres_repository.claim_target(
            request_id="r1",
            game_id="g1",
            target_seq=7,
            scope="move",
            round_span=None,
            force=False,
        )

    results = await asyncio.gather(*(claim() for _ in range(16)))
    winners = [r for r in results if r.claimed]
    assert len(winners) == 1
