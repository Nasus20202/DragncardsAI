"""The worker's live-push side of evaluation error reporting.

A failure recorded on a target row is only *reported* if the live channel is
woken, so a connected stream re-reads the snapshot that now carries it. These
tests cover that wiring: the worker pushes on a mid-evaluation attempt failure,
on a terminal failure, and on a per-game history read failure.
"""

from __future__ import annotations

import pytest

from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostError
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.live_events import LiveEventBus
from eval_service.runtime.requests import RequestService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schemas.api import EvaluationRequestBody, Selection
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        evaluator_version="eval-1",
        eval_max_attempts=3,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


def _events(game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2, action="play"),
        state_event(game_id=game_id, seq=3, round_number=1),
    ]


def _wire(repository, history, judge, settings, bus):
    evaluator = Evaluator(
        settings=settings, repository=repository, history=history, judge=judge
    )
    request_service = RequestService(
        settings=settings, repository=repository, history=history
    )
    worker = EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=evaluator,
        live_bus=bus,
    )
    return request_service, worker


def _drain_queue(queue):
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    return events


@pytest.mark.asyncio
async def test_failing_attempts_wake_live_subscribers_before_the_run_ends(repository):
    history = FakeHistoryClient({"g1": _events()})
    judge = StubJudgeClient(fail_times=2)
    bus = LiveEventBus()
    request_service, worker = _wire(repository, history, judge, _settings(), bus)
    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )
    queue = bus.subscribe(resp.request_id)

    await worker.drain_once()

    # One push per failed attempt, on top of the running/terminal transitions --
    # so a watching client is woken while the evaluation is still in flight.
    pushes = _drain_queue(queue)
    assert len(pushes) >= 4
    assert all(event == "status" for event, _data in pushes)


@pytest.mark.asyncio
async def test_history_read_failure_is_recorded_as_failed_and_pushed(repository):
    class BrokenHistory(FakeHistoryClient):
        """Reads fine while the request is created, then breaks for the drain."""

        explode = False

        async def list_all_events(self, game_id: str):
            if self.explode:
                raise RuntimeError("history unavailable")
            return await super().list_all_events(game_id)

    history = BrokenHistory({"g1": _events()})
    judge = StubJudgeClient()
    bus = LiveEventBus()
    request_service, worker = _wire(repository, history, judge, _settings(), bus)
    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )
    queue = bus.subscribe(resp.request_id)
    history.explode = True

    await worker.drain_once()

    targets = await repository.list_targets_for_request(resp.request_id)
    assert [t.status for t in targets] == ["failed"]
    assert "history read failed" in targets[0].error
    assert _drain_queue(queue), "the failure must wake live subscribers"


@pytest.mark.asyncio
async def test_terminal_judge_failure_reaches_the_target_result(repository):
    from eval_service.runtime.status import to_target_result

    history = FakeHistoryClient({"g1": _events()})
    judge = StubJudgeClient(
        error=BifrostError("gateway_error", "judge key missing", retryable=False)
    )
    bus = LiveEventBus()
    request_service, worker = _wire(repository, history, judge, _settings(), bus)
    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )

    await worker.drain_once()

    targets = await repository.list_targets_for_request(resp.request_id)
    result = to_target_result(targets[0])
    # The API/stream projection carries the detail, not just the status.
    assert result.status == "failed"
    assert "judge key missing" in result.error
