from __future__ import annotations

import asyncio
from collections import Counter

import pytest

from eval_service.config import Settings
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.requests import RequestService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schemas.api import EvaluationRequestBody, Selection
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)

pytestmark = pytest.mark.postgres


def _recorded_game(game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2, action="play_a"),
        state_event(game_id=game_id, seq=3, round_number=1),
        agent_event(game_id=game_id, seq=4, action="play_b"),
        state_event(game_id=game_id, seq=5, round_number=2),
        agent_event(game_id=game_id, seq=6, action="attack"),
        state_event(game_id=game_id, seq=7, round_number=2, status="win"),
    ]


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        evaluator_version="eval-1",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


class CountingJudgeClient(StubJudgeClient):
    """A judge stub that records how many times each target_seq was graded.

    Verdicts are derived from the move's seq so we can attribute each judge
    call to a specific target, proving each target is evaluated at most once.
    """

    def __init__(self) -> None:
        super().__init__()
        self.seq_calls: Counter[int] = Counter()
        self._lock = asyncio.Lock()

    async def judge(self, *, model, messages, max_tokens, gateway_options=None) -> str:
        # A small await yields control so concurrent drainers interleave,
        # maximizing the chance a duplicate claim would be observed.
        await asyncio.sleep(0)
        text = " ".join(
            str(m.get("content", "")) for m in messages if isinstance(m, dict)
        )
        # Attribute the call by the prompt's own statement of which move it grades.
        # NOT by the move's arguments: a move prompt also carries a window of the
        # neighbouring moves, so their arguments appear in it too.
        async with self._lock:
            for seq in (2, 4, 6):
                if f"single agent move (seq {seq})" in text:
                    self.seq_calls[seq] += 1
        return await super().judge(
            model=model, messages=messages, max_tokens=max_tokens
        )


@pytest.mark.asyncio
async def test_two_concurrent_drains_evaluate_each_target_once(postgres_repository):
    """Two replicas draining the same pending targets concurrently must each
    evaluate every target at most once (M1: exclusive cross-replica claims)."""
    events = _recorded_game()
    history = FakeHistoryClient({"g1": events})
    judge = CountingJudgeClient()
    settings = _settings()

    evaluator = Evaluator(
        settings=settings,
        repository=postgres_repository,
        history=history,
        judge=judge,
    )
    request_service = RequestService(
        settings=settings, repository=postgres_repository, history=history
    )
    # Two independent workers sharing the same Postgres repository simulate two
    # service replicas draining the same backlog.
    worker_a = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=evaluator,
    )
    worker_b = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=evaluator,
    )

    resp = await request_service.create(
        "g1",
        EvaluationRequestBody(scope="move", selection=Selection(seqs=[2, 4, 6])),
    )
    assert resp.created_count == 3

    # Drain concurrently from both "replicas".
    await asyncio.gather(worker_a.drain_once(), worker_b.drain_once())

    targets = await postgres_repository.list_targets_for_request(resp.request_id)
    assert {t.status for t in targets} == {"completed"}
    # Each selected target was judged exactly once across both drainers.
    assert dict(judge.seq_calls) == {2: 1, 4: 1, 6: 1}
    # One advisory verdict per target was written back (no duplicates).
    written_seqs = sorted(e["payload"]["target_seq"] for _, e in history.written)
    assert written_seqs == [2, 4, 6]


def _many_move_game(game_id: str, move_count: int):
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


@pytest.mark.asyncio
async def test_durable_claim_bounds_concurrency_across_replicas(postgres_repository):
    """The per-game cap holds across replicas because it lives in the claim.

    The cap used to be a process-local semaphore, which two replicas could each
    honour separately and still exceed together. It is now computed inside the
    claiming transaction from the rows already recorded ``running``, so a second
    drainer sees the first drainer's in-flight work. On real PostgreSQL the claim
    also takes ``FOR UPDATE SKIP LOCKED``, which sqlite omits — so this is the
    only place the locking path is actually exercised.
    """
    seqs = list(range(2, 12))
    await postgres_repository.create_request(
        request_id="r-cap",
        game_id="gcap",
        scope="move",
        selection={"seqs": seqs},
        force=False,
    )
    for seq in seqs:
        await postgres_repository.claim_target(
            request_id="r-cap",
            game_id="gcap",
            target_seq=seq,
            scope="move",
            round_span=None,
            force=False,
        )

    first = await postgres_repository.claim_pending_targets(
        per_game_limit=3, global_limit=8
    )
    assert len(first) == 3
    # Those three are recorded ``running``, so a concurrent replica gets nothing.
    second = await postgres_repository.claim_pending_targets(
        per_game_limit=3, global_limit=8
    )
    assert second == []

    # Capacity frees up only as in-flight work reaches a terminal state.
    await postgres_repository.finalize_completed(first[0].id, {"overall_score": 7})
    third = await postgres_repository.claim_pending_targets(
        per_game_limit=3, global_limit=8
    )
    assert len(third) == 1
    assert third[0].id not in {t.id for t in first}


@pytest.mark.asyncio
async def test_parallel_drain_of_a_whole_round_loses_nothing(postgres_repository):
    """A round's worth of moves drains in parallel with no loss or duplication."""
    seqs = list(range(2, 12))
    events = _many_move_game("gpar", move_count=10)
    history = FakeHistoryClient({"gpar": events})
    judge = StubJudgeClient()
    settings = _settings(eval_per_game_concurrency=4, eval_global_concurrency=8)
    worker = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=Evaluator(
            settings=settings,
            repository=postgres_repository,
            history=history,
            judge=judge,
        ),
    )
    request_service = RequestService(
        settings=settings, repository=postgres_repository, history=history
    )
    resp = await request_service.create(
        "gpar",
        EvaluationRequestBody(scope="move", selection=Selection(seqs=seqs)),
    )
    assert resp.created_count == len(seqs)

    # Each cycle claims only the remaining capacity, so several are needed.
    cycles = 0
    while cycles < 20:
        cycles += 1
        if await worker.drain_once() == 0:
            break
    assert cycles > 1, "the capacity-bounded claim should need more than one cycle"

    targets = await postgres_repository.list_targets_for_request(resp.request_id)
    assert len(targets) == len(seqs)
    # Nothing lost: every target terminal, every one carrying a verdict.
    assert {t.status for t in targets} == {"completed"}
    assert all(t.verdict_json is not None for t in targets)
    # Nothing duplicated: exactly one write-back per target.
    written = sorted(e["payload"]["target_seq"] for _, e in history.written)
    assert written == seqs
