from __future__ import annotations

import pytest

from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostError
from eval_service.judge.config import SkillResolver, resolve_judge_config
from eval_service.judge.writeback import verdict_idempotency_key
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.requests import RequestService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schemas.api import EvaluationRequestBody, JudgeConfig, Selection
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
        eval_max_attempts=2,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


def _wire(postgres_repository, history, judge, settings):
    evaluator = Evaluator(
        settings=settings,
        repository=postgres_repository,
        history=history,
        judge=judge,
    )
    request_service = RequestService(
        settings=settings, repository=postgres_repository, history=history
    )
    worker = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=evaluator,
    )
    return request_service, worker


@pytest.mark.asyncio
async def test_move_request_produces_one_verdict_per_selected_move(
    postgres_repository,
):
    events = _recorded_game()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    request_service, worker = _wire(postgres_repository, history, judge, _settings())

    resp = await request_service.create(
        "g1",
        EvaluationRequestBody(scope="move", selection=Selection(seqs=[2, 6])),
    )
    assert resp.created_count == 2

    await worker.drain_once()

    targets = await postgres_repository.list_targets_for_request(resp.request_id)
    assert all(t.status == "completed" for t in targets)
    # One evaluator event per selected move; seq4 (unselected) is never graded.
    written_seqs = sorted(e["payload"]["target_seq"] for _, e in history.written)
    assert written_seqs == [2, 6]


@pytest.mark.asyncio
async def test_round_request_produces_one_verdict_per_closed_round(
    postgres_repository,
):
    events = _recorded_game()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    request_service, worker = _wire(postgres_repository, history, judge, _settings())

    resp = await request_service.create(
        "g1",
        EvaluationRequestBody(scope="round", selection=Selection(whole_game=True)),
    )
    # Cascade: a round-scope request auto-grades each round's child moves
    # (seq 2, 4, 6) and rolls each closed round up into a per-player verdict.
    assert resp.created_count == 5
    round_targets = sorted(
        (t.target_seq, tuple(t.round_span)) for t in resp.targets if t.scope == "round"
    )
    # round 1 closes at seq4 (span 1-4); round 2 (terminal) at seq7 (span 5-7).
    assert round_targets == [(4, (1, 4)), (7, (5, 7))]

    # A round roll-up defers itself while its child moves are still in flight,
    # so the cascade completes over successive drains (as run_forever loops).
    # Drain to quiescence, mirroring the worker loop.
    for _ in range(10):
        if await worker.drain_once() == 0:
            break

    round_written = sorted(
        (e["payload"]["target_seq"], tuple(e["payload"]["round_span"]))
        for _, e in history.written
        if e["payload"]["scope"] == "round"
    )
    assert round_written == [(4, (1, 4)), (7, (5, 7))]


@pytest.mark.asyncio
async def test_duplicate_writeback_stored_once(postgres_repository):
    events = _recorded_game()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    settings = _settings()
    request_service, worker = _wire(postgres_repository, history, judge, settings)
    body = EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    await request_service.create("g1", body)
    await worker.drain_once()

    # Force a re-evaluation with the SAME config -> same idempotency key ->
    # history stores once.
    resp2 = await request_service.create(
        "g1",
        EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]), force=True),
    )
    assert resp2.created_count == 1
    await worker.drain_once()

    # The request flow always resolves a judge config; the key folds it in.
    # The move at seq2 attributes to player1, which is part of the key too.
    resolved = resolve_judge_config(settings, None, SkillResolver(()))
    key = verdict_idempotency_key("g1", 2, "move", "eval-1", resolved, "player1")
    matching = [e for _, e in history.written if e["idempotency_key"] == key]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_forced_reeval_with_different_config_is_not_deduped(postgres_repository):
    # A forced re-eval under a DIFFERENT judge config must produce a DISTINCT
    # history event instead of being silently dropped by history dedup.
    events = _recorded_game()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    settings = _settings()
    request_service, worker = _wire(postgres_repository, history, judge, settings)

    await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )
    await worker.drain_once()

    # Force a re-eval with a different model (distinct resolved config).
    resp2 = await request_service.create(
        "g1",
        EvaluationRequestBody(
            scope="move",
            selection=Selection(seqs=[2]),
            force=True,
            judge=JudgeConfig(model_name="openai/gpt-z"),
        ),
    )
    assert resp2.created_count == 1
    await worker.drain_once()

    keys = {e["idempotency_key"] for _, e in history.written}
    # Two distinct verdicts retained (one per config), not deduped to one.
    assert len(keys) == 2
    assert len(history.written) == 2


@pytest.mark.asyncio
async def test_failing_judge_skips_without_blocking_others(postgres_repository):
    events = _recorded_game()
    history = FakeHistoryClient({"g1": events})
    # Judge always fails -> all targets skipped, none block the others.
    judge = StubJudgeClient(error=BifrostError("gateway_error", "down", retryable=True))
    request_service, worker = _wire(
        postgres_repository, history, judge, _settings(eval_max_attempts=1)
    )
    resp = await request_service.create(
        "g1",
        EvaluationRequestBody(scope="move", selection=Selection(seqs=[2, 4, 6])),
    )
    await worker.drain_once()

    targets = await postgres_repository.list_targets_for_request(resp.request_id)
    assert {t.status for t in targets} == {"skipped"}
    # A judge outage never writes advisory events and never errors out the batch.
    assert history.written == []
