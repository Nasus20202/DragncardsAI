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
