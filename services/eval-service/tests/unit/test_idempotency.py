from __future__ import annotations

import asyncio

import pytest


async def _seed_request(repository, request_id="r1", game_id="g1"):
    await repository.create_request(
        request_id=request_id,
        game_id=game_id,
        scope="move",
        selection={"seqs": [2]},
        force=False,
    )


@pytest.mark.asyncio
async def test_claim_is_at_most_once(repository):
    await _seed_request(repository)
    first = await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
    )
    assert first.claimed is True

    # A second claim without force is a no-op (already evaluated/in-flight).
    second = await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
    )
    assert second.claimed is False
    assert second.existing_status == "pending"


@pytest.mark.asyncio
async def test_force_reclaims_and_resets(repository):
    await _seed_request(repository)
    claim = await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
    )
    await repository.finalize_completed(claim.target_id, {"overall_score": 7})

    forced = await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=True,
    )
    assert forced.claimed is True
    row = await repository.get_target_by_id(forced.target_id)
    assert row.status == "pending"
    assert row.verdict_json is None


@pytest.mark.asyncio
async def test_same_seq_different_scope_does_not_collide(repository):
    await _seed_request(repository)
    move = await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=5,
        scope="move",
        round_span=None,
        force=False,
    )
    rnd = await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=5,
        scope="round",
        round_span=(1, 5),
        force=False,
    )
    assert move.claimed is True
    assert rnd.claimed is True
    assert move.target_id != rnd.target_id


@pytest.mark.asyncio
async def test_same_seq_different_platform_does_not_collide(repository):
    await _seed_request(repository, request_id="dragncards", game_id="shared")
    await _seed_request(repository, request_id="marvel", game_id="shared")
    dragncards = await repository.claim_target(
        request_id="dragncards",
        game_id="shared",
        platform="dragncards",
        target_seq=5,
        scope="move",
        round_span=None,
        force=False,
    )
    marvel = await repository.claim_target(
        request_id="marvel",
        game_id="shared",
        platform="marvel-lcg",
        target_seq=5,
        scope="move",
        round_span=None,
        force=False,
    )
    assert dragncards.claimed is True
    assert marvel.claimed is True
    assert dragncards.target_id != marvel.target_id


@pytest.mark.asyncio
async def test_concurrent_claims_resolve_to_single(repository):
    await _seed_request(repository)

    async def claim():
        return await repository.claim_target(
            request_id="r1",
            game_id="g1",
            target_seq=9,
            scope="move",
            round_span=None,
            force=False,
        )

    results = await asyncio.gather(*(claim() for _ in range(8)))
    winners = [r for r in results if r.claimed]
    assert len(winners) == 1
