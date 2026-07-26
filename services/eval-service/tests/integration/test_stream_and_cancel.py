from __future__ import annotations

import asyncio
import json

import pytest

from eval_service.config import Settings
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.inflight import InflightRegistry
from eval_service.runtime.live_events import LiveEventBus
from eval_service.runtime.requests import RequestService
from eval_service.runtime.stream import EvaluationStreamService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schemas.api import EvaluationRequestBody, JudgeConfig, Selection
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)

pytestmark = pytest.mark.postgres


def _game(game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2),
        state_event(game_id=game_id, seq=3, round_number=1, status="win"),
    ]


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


def _parse_sse(chunk: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in chunk.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(":"):
            continue
        name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        if name is not None:
            events.append((name, data))
    return events


@pytest.mark.asyncio
async def test_stream_emits_status_and_verdict(postgres_repository):
    repo = postgres_repository
    settings = _settings()
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    live_bus = LiveEventBus()
    inflight = InflightRegistry()
    evaluator = Evaluator(
        settings=settings, repository=repo, history=history, judge=judge
    )
    request_service = RequestService(
        settings=settings, repository=repo, history=history
    )
    worker = EvaluationWorker(
        settings=settings,
        repository=repo,
        history=history,
        evaluator=evaluator,
        live_bus=live_bus,
        inflight=inflight,
    )
    stream_service = EvaluationStreamService(repository=repo, live_bus=live_bus)

    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )
    request_id = resp.request_id

    collected: list[tuple[str, dict]] = []

    async def consume() -> None:
        async for chunk in stream_service.stream(request_id):
            collected.extend(_parse_sse(chunk))

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0.05)  # let the stream emit the initial snapshot
    await worker.drain_once()
    await asyncio.wait_for(consumer, timeout=5)

    names = [n for n, _ in collected]
    assert names[0] == "status"  # initial snapshot
    assert "verdict" in names
    assert names[-1] == "done"
    done = [d for n, d in collected if n == "done"][0]
    assert done["status"] == "completed"
    verdict = [d for n, d in collected if n == "verdict"][0]
    assert verdict["target_seq"] == 2
    assert verdict["verdict"]["evaluator"]["model"] == "anthropic/claude-x"


@pytest.mark.asyncio
async def test_cancel_transitions_targets_and_closes_stream(postgres_repository):
    repo = postgres_repository
    settings = _settings()
    history = FakeHistoryClient({"g1": _game()})

    # A judge that blocks until released, so the target is genuinely in-flight
    # when we cancel it.
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingJudge(StubJudgeClient):
        async def judge(self, *, model, messages, max_tokens, gateway_options=None):
            started.set()
            await release.wait()  # cancelled here by task cancellation
            return await super().judge(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                gateway_options=gateway_options,
            )

    judge = BlockingJudge()
    live_bus = LiveEventBus()
    inflight = InflightRegistry()
    evaluator = Evaluator(
        settings=settings, repository=repo, history=history, judge=judge
    )
    request_service = RequestService(
        settings=settings, repository=repo, history=history
    )
    worker = EvaluationWorker(
        settings=settings,
        repository=repo,
        history=history,
        evaluator=evaluator,
        live_bus=live_bus,
        inflight=inflight,
    )
    stream_service = EvaluationStreamService(repository=repo, live_bus=live_bus)

    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )
    request_id = resp.request_id

    collected: list[tuple[str, dict]] = []

    async def consume() -> None:
        async for chunk in stream_service.stream(request_id):
            collected.extend(_parse_sse(chunk))

    consumer = asyncio.create_task(consume())
    drain = asyncio.create_task(worker.drain_once())

    # Wait until the judge call is genuinely in-flight, then cancel.
    await asyncio.wait_for(started.wait(), timeout=5)
    cancelled_ids = await repo.cancel_request_targets(request_id)
    assert len(cancelled_ids) == 1
    for target_id in cancelled_ids:
        inflight.cancel(target_id)
    live_bus.publish(request_id, "status", {"request_id": request_id})

    release.set()  # unblock (the task is already cancelled)
    await asyncio.wait_for(drain, timeout=5)
    await asyncio.wait_for(consumer, timeout=5)

    targets = await repo.list_targets_for_request(request_id)
    assert all(t.status == "cancelled" for t in targets)
    # No verdict written for a cancelled target.
    assert all(t.verdict_json is None for t in targets)
    assert history.written == []

    names = [n for n, _ in collected]
    assert names[-1] == "done"
    done = [d for n, d in collected if n == "done"][0]
    assert done["status"] == "cancelled"


@pytest.mark.asyncio
async def test_force_reclaim_while_running_writes_single_verdict(postgres_repository):
    # A force re-claim that lands while a worker is mid-evaluation on the target
    # must cancel the in-flight task, so exactly ONE verdict is written back
    # (never a stale + a fresh one). The stale task is deliberately paused INSIDE
    # ``write_event`` — i.e. it has already passed the ``running`` re-check — so
    # the durable re-check alone cannot prevent the double write-back; only
    # cancelling the in-flight task can. The two requests use DIFFERENT judge
    # models so their idempotency keys differ and history dedup cannot mask a
    # double write-back.
    repo = postgres_repository
    settings = _settings()

    write_started = asyncio.Event()
    write_release = asyncio.Event()

    class BlockingWriteHistory(FakeHistoryClient):
        async def write_event(self, game_id, envelope):
            write_started.set()
            await write_release.wait()  # stale write is cancelled here
            return await super().write_event(game_id, envelope)

    history = BlockingWriteHistory({"g1": _game()})
    judge = StubJudgeClient()
    inflight = InflightRegistry()
    evaluator = Evaluator(
        settings=settings, repository=repo, history=history, judge=judge
    )
    # RequestService MUST share the same registry as the worker so a force
    # re-claim can abort the worker's in-flight task.
    request_service = RequestService(
        settings=settings, repository=repo, history=history, inflight=inflight
    )
    worker = EvaluationWorker(
        settings=settings,
        repository=repo,
        history=history,
        evaluator=evaluator,
        inflight=inflight,
    )

    resp = await request_service.create(
        "g1", EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    )
    (first_target,) = await repo.list_targets_for_request(resp.request_id)

    # Start the first evaluation; it runs the judge, passes the ``running``
    # re-check, and then blocks INSIDE write_event.
    drain = asyncio.create_task(worker.drain_once())
    await asyncio.wait_for(write_started.wait(), timeout=5)

    # Force re-claim the SAME target with a different judge model. This resets
    # the row to pending and MUST cancel the first task (blocked in write_event).
    await request_service.create(
        "g1",
        EvaluationRequestBody(
            scope="move",
            selection=Selection(seqs=[2]),
            force=True,
            judge=JudgeConfig(model_name="anthropic/claude-y"),
        ),
    )

    write_release.set()  # unblock; the stale write is already cancelled
    await asyncio.wait_for(drain, timeout=5)

    # The stale task's write-back was cancelled before it committed.
    assert history.written == []

    # A second drain grades the freshly re-claimed target exactly once.
    await asyncio.wait_for(worker.drain_once(), timeout=5)

    assert len(history.written) == 1
    _game_id, envelope = history.written[0]
    # The FRESH config won: the verdict records the re-claim's model, not the
    # stale first evaluation's model.
    assert envelope["payload"]["evaluator"]["model"] == "anthropic/claude-y"

    row = await repo.get_target_by_id(first_target.id)
    assert row.status == "completed"
