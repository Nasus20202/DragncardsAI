from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from eval_service.config import Settings
from eval_service.judge.config import ResolvedJudgeConfig, ResolvedReasoning
from eval_service.runtime.evaluator import Evaluator
from eval_service.schema_migrations import ensure_schema
from eval_service.storage.db import create_session_factory
from eval_service.storage.repository import Repository
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)


@pytest_asyncio.fixture
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    yield Repository(create_session_factory(engine))
    await engine.dispose()


def _events(game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2),
        state_event(game_id=game_id, seq=3, round_number=1, status="win"),
    ]


async def _claim_running_target(repo, judge_config) -> int:
    await repo.create_request(
        request_id="r1",
        game_id="g1",
        scope="move",
        selection={"seqs": [2]},
        force=False,
        judge_config=judge_config,
    )
    claim = await repo.claim_target(
        request_id="r1",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
        judge_config=judge_config,
    )
    # Move it to running (as the worker would).
    claimed = await repo.claim_pending_targets(limit=10)
    assert claimed
    return claim.target_id


@pytest.mark.asyncio
async def test_verdict_records_actual_model_and_provider(repo):
    settings = Settings(eval_judge_model="anthropic/default", eval_max_attempts=1)
    history = FakeHistoryClient({"g1": _events()})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=settings, repository=repo, history=history, judge=judge
    )
    config = ResolvedJudgeConfig(
        model="openrouter/google/gemma:free",
        provider="openrouter",
        reasoning=ResolvedReasoning(enabled=True, effort="high", max_tokens=128),
        prompt_override=None,
        skills=(),
    )
    target_id = await _claim_running_target(repo, config.to_json())

    await evaluator.evaluate_target(
        target_id=target_id,
        game_id="g1",
        target_seq=2,
        scope="move",
        events=_events(),
        judge_config=config,
    )

    target = await repo.get_target_by_id(target_id)
    assert target.status == "completed"
    evaluator_meta = target.verdict_json["evaluator"]
    assert evaluator_meta["model"] == "openrouter/google/gemma:free"
    assert evaluator_meta["provider"] == "openrouter"
    # The reasoning mapping reached the judge call as gateway_options.
    assert judge.calls[0]["model"] == "openrouter/google/gemma:free"
    assert judge.calls[0]["gateway_options"] == {
        "reasoning": {"effort": "high", "max_tokens": 128}
    }


@pytest.mark.asyncio
async def test_no_model_configured_fails(repo):
    settings = Settings(eval_judge_model="", eval_max_attempts=1)
    history = FakeHistoryClient({"g1": _events()})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=settings, repository=repo, history=history, judge=judge
    )
    target_id = await _claim_running_target(repo, None)
    with pytest.raises(Exception):
        await evaluator.evaluate_target(
            target_id=target_id,
            game_id="g1",
            target_seq=2,
            scope="move",
            events=_events(),
            judge_config=None,
        )
    target = await repo.get_target_by_id(target_id)
    assert target.status == "failed"
