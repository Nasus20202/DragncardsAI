from __future__ import annotations

import asyncio

import pytest

from eval_service.config import Settings
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.worker import EvaluationWorker
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


def _game(game_id: str, move_count: int):
    """One round holding ``move_count`` agent moves, closed by a terminal state."""
    events = [state_event(game_id=game_id, seq=1, round_number=0)]
    events += [
        agent_event(game_id=game_id, seq=seq, action="move_card")
        for seq in range(2, 2 + move_count)
    ]
    events.append(
        state_event(game_id=game_id, seq=2 + move_count, round_number=1, status="win")
    )
    return events


async def _enqueue_moves(repository, game_id: str, seqs: list[int], request_id: str):
    await repository.create_request(
        request_id=request_id,
        game_id=game_id,
        scope="move",
        selection={"seqs": seqs},
        force=False,
    )
    for seq in seqs:
        await repository.claim_target(
            request_id=request_id,
            game_id=game_id,
            target_seq=seq,
            scope="move",
            round_span=None,
            force=False,
        )


class ConcurrencyProbe(StubJudgeClient):
    """A judge that records how many calls are in flight at the same time.

    Yields to the event loop inside the call so genuinely parallel evaluations
    overlap, which is what makes ``max_concurrent`` meaningful.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.in_flight = 0
        self.max_concurrent = 0

    async def judge(self, **kwargs) -> str:
        self.in_flight += 1
        self.max_concurrent = max(self.max_concurrent, self.in_flight)
        try:
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            return await super().judge(**kwargs)
        finally:
            self.in_flight -= 1


@pytest.mark.asyncio
async def test_claim_respects_the_per_game_cap_from_durable_state(repository):
    # Ten pending targets, per-game cap of 3: the claim itself -- not a semaphore
    # -- must hand back only 3, and hand back none while those 3 are running.
    await _enqueue_moves(repository, "g1", list(range(2, 12)), "r1")

    first = await repository.claim_pending_targets(per_game_limit=3, global_limit=8)
    assert len(first) == 3
    assert all(t.status == "running" for t in first)

    # Capacity is computed from the recorded ``running`` rows, so a second drain
    # while those are still in flight gets nothing. This is what makes the cap
    # survive a restart and hold for a second replica.
    second = await repository.claim_pending_targets(per_game_limit=3, global_limit=8)
    assert second == []

    await repository.mark_skipped(first[0].id, "done")
    third = await repository.claim_pending_targets(per_game_limit=3, global_limit=8)
    assert len(third) == 1


@pytest.mark.asyncio
async def test_claim_respects_the_global_cap_across_games(repository):
    await _enqueue_moves(repository, "g1", [2, 3, 4], "r1")
    await _enqueue_moves(repository, "g2", [2, 3, 4], "r2")

    claimed = await repository.claim_pending_targets(per_game_limit=3, global_limit=4)
    assert len(claimed) == 4
    # The global cap bounds the total, not each game, so both games are drawn from.
    assert {t.game_id for t in claimed} == {"g1", "g2"}


@pytest.mark.asyncio
async def test_claim_without_caps_is_unbounded(repository):
    await _enqueue_moves(repository, "g1", list(range(2, 12)), "r1")
    claimed = await repository.claim_pending_targets()
    assert len(claimed) == 10


@pytest.mark.asyncio
async def test_parallel_drain_loses_and_duplicates_nothing(repository):
    """Every claimed target ends terminal exactly once, with exactly one verdict."""
    seqs = list(range(2, 14))  # 12 moves in one round
    events = _game("g1", move_count=12)
    history = FakeHistoryClient({"g1": events})
    judge = ConcurrencyProbe()
    settings = _settings(eval_per_game_concurrency=4, eval_global_concurrency=8)
    worker = EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=Evaluator(
            settings=settings, repository=repository, history=history, judge=judge
        ),
    )
    await _enqueue_moves(repository, "g1", seqs, "r1")

    total = 0
    for _ in range(20):
        progressed = await worker.drain_once()
        total += progressed
        if progressed == 0:
            break

    targets = await repository.list_targets_for_request("r1")
    assert len(targets) == len(seqs)
    # Nothing lost: no target left non-terminal, and every one has a verdict.
    assert {t.status for t in targets} == {"completed"}
    assert all(t.verdict_json is not None for t in targets)
    # Nothing duplicated: one judge call and one history write-back per target.
    assert len(judge.calls) == len(seqs)
    assert len(history.written) == len(seqs)
    assert total == len(seqs)
    # And it really was parallel, bounded by the per-game cap.
    assert judge.max_concurrent > 1
    assert judge.max_concurrent <= settings.eval_per_game_concurrency


@pytest.mark.asyncio
async def test_parallelism_is_bounded_by_the_per_game_cap(repository):
    seqs = list(range(2, 14))
    events = _game("g1", move_count=12)
    history = FakeHistoryClient({"g1": events})
    judge = ConcurrencyProbe()
    settings = _settings(eval_per_game_concurrency=2, eval_global_concurrency=8)
    worker = EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=Evaluator(
            settings=settings, repository=repository, history=history, judge=judge
        ),
    )
    await _enqueue_moves(repository, "g1", seqs, "r1")

    for _ in range(20):
        if await worker.drain_once() == 0:
            break
    # A game-wide evaluation must not stampede the provider.
    assert judge.max_concurrent <= 2


@pytest.mark.asyncio
async def test_all_deferred_cycle_reports_no_progress(repository):
    """A roll-up waiting on its children is not progress, so the worker can idle.

    Reporting a deferral as handled would make ``run_forever`` skip its poll wait
    and hot-loop on the database for as long as the children take.
    """
    events = _game("g1", move_count=2)
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    settings = _settings(eval_per_game_concurrency=1)
    worker = EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=Evaluator(
            settings=settings, repository=repository, history=history, judge=judge
        ),
    )
    await repository.create_request(
        request_id="r1",
        game_id="g1",
        scope="round",
        selection={"rounds": [0]},
        force=False,
    )
    # A round roll-up plus one still-pending child move it depends on. The move is
    # claimed as pending but held back from this drain by the per-game cap of 1, so
    # the roll-up is the only thing drained and it can only defer.
    await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
    )
    await repository.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=4,
        scope="round",
        round_span=(1, 4),
        force=False,
    )
    # Take the move's slot so only the roll-up is available to the worker's drain.
    held = await repository.claim_pending_targets(per_game_limit=1)
    assert [t.scope for t in held] == ["move"]

    assert await worker.drain_once() == 0
    assert judge.calls == []
    # And the roll-up is back to pending, ready for a later drain.
    round_target = next(
        t for t in await repository.list_targets_for_request("r1") if t.scope == "round"
    )
    assert round_target.status == "pending"
