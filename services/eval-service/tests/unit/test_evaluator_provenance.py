from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from eval_service.config import Settings
from eval_service.judge.config import ResolvedJudgeConfig, ResolvedReasoning
from eval_service.runtime.evaluator import Evaluator
from eval_service.schema_migrations import ensure_schema
from eval_service.schemas.history import PLATFORM_MARVEL_LCG
from eval_service.storage.db import create_session_factory
from eval_service.storage.repository import Repository
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    marvel_producer_event,
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


def _normalized_marvel_state(*, threat: int, mode: str = "in progress") -> dict:
    return {
        "playRound": 1,
        "phase": "player",
        "phaseLabel": "Player turn",
        "mode": mode,
        "players": {"player1": {"handSize": 4}},
        "zones": {
            "sharedMainScheme": [
                {
                    "name": "The Break-In!",
                    "tokens": {"threat": threat},
                }
            ]
        },
    }


def _marvel_move_event(
    *,
    game_id: str,
    seq: int,
    action: str,
    reasoning: str,
    arguments: dict | None = None,
    prompt_provenance: dict | None = None,
):
    payload = {
        "intended_action": action,
        "reasoning": reasoning,
        "arguments": arguments if arguments is not None else {"option_id": "option-7"},
    }
    if prompt_provenance is not None:
        payload["prompt_provenance"] = prompt_provenance
    return agent_event(game_id=game_id, seq=seq).model_copy(
        update={
            "platform": PLATFORM_MARVEL_LCG,
            "payload": payload,
        }
    )


def _marvel_judge_config() -> ResolvedJudgeConfig:
    return ResolvedJudgeConfig(
        model="openrouter/google/gemma:free",
        provider="openrouter",
        reasoning=ResolvedReasoning(enabled=True, effort="high", max_tokens=128),
        prompt_override=None,
        skills=(),
    )


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


async def _evaluate_marvel_move(repo, events):
    settings = Settings(eval_judge_model="anthropic/default", eval_max_attempts=1)
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=settings, repository=repo, history=history, judge=judge
    )
    config = _marvel_judge_config()
    target_id = await _claim_running_target(repo, config.to_json())
    await evaluator.evaluate_target(
        target_id=target_id,
        game_id="g1",
        platform=PLATFORM_MARVEL_LCG,
        target_seq=2,
        scope="move",
        events=events,
        judge_config=config,
    )
    return await repo.get_target_by_id(target_id), judge


@pytest.mark.asyncio
async def test_marvel_terminal_loss_overrides_positive_judge_verdict(repo):
    events = [
        marvel_producer_event(
            game_id="g1",
            seq=1,
            state=_normalized_marvel_state(threat=12),
        ),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="decline",
            reasoning="This is a safe, strategically strong choice.",
        ),
        marvel_producer_event(
            game_id="g1",
            seq=3,
            state=_normalized_marvel_state(threat=14, mode="loss"),
        ),
    ]

    target, judge = await _evaluate_marvel_move(repo, events)

    assert target.status == "completed"
    assert target.verdict_json["overall_score"] == 0
    assert target.verdict_json["scores"] == {
        "rules_legality": 0,
        "strategic_quality": 0,
        "tempo_efficiency": 0,
        "threat_resource": 0,
    }
    assert "terminal_loss" in target.verdict_json["flags"]
    assert judge.calls


@pytest.mark.asyncio
async def test_marvel_unchanged_threat_cannot_credit_coordinator_claim(repo):
    provenance = {
        "source": "coordinator",
        "prompt": "Use this rule: remove two threat from the main scheme.",
        "orchestrator_session_id": "orchestrator-1",
        "parent_job_id": "parent-1",
        "child_job_id": "child-1",
    }
    events = [
        marvel_producer_event(
            game_id="g1",
            seq=1,
            state=_normalized_marvel_state(threat=12),
        ),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="choose_game_option",
            reasoning="I am removing two threat from the main scheme as instructed.",
            prompt_provenance=provenance,
        ),
        marvel_producer_event(
            game_id="g1",
            seq=3,
            state=_normalized_marvel_state(threat=12),
        ),
    ]

    target, judge = await _evaluate_marvel_move(repo, events)

    assert target.verdict_json["overall_score"] == 0
    assert target.verdict_json["scores"]["threat_resource"] == 0
    assert "unobserved_threat_removal" in target.verdict_json["flags"]
    assert "coordinator_instruction_conflict" in target.verdict_json["flags"]
    prompt_text = "\n".join(
        str(message.get("content", ""))
        for message in judge.calls[0]["messages"]
        if isinstance(message, dict)
    )
    assert "UNTRUSTED EVIDENCE" in prompt_text
    assert "orchestrator-1" in prompt_text


@pytest.mark.asyncio
async def test_coordinator_prompt_with_unchosen_threat_option_does_not_zero_player_move(
    repo,
):
    provenance = {
        "source": "coordinator",
        "prompt": (
            "CURRENT ENGINE PROMPT\n"
            "  1. Thwart — remove 2 threat from the main scheme\n"
            "  2. Attack Rhino — deal 3 damage\n"
            "  3. End turn"
        ),
        "orchestrator_session_id": "orchestrator-1",
        "parent_job_id": "parent-1",
        "child_job_id": "child-1",
    }
    events = [
        marvel_producer_event(
            game_id="g1",
            seq=1,
            state=_normalized_marvel_state(threat=12),
        ),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="choose_game_option",
            arguments={"option_id": "2"},
            reasoning="I choose option 2 to attack Rhino and deal damage.",
            prompt_provenance=provenance,
        ),
        marvel_producer_event(
            game_id="g1",
            seq=3,
            state=_normalized_marvel_state(threat=12),
        ),
    ]

    target, judge = await _evaluate_marvel_move(repo, events)

    assert target.verdict_json["overall_score"] == 7
    assert target.verdict_json["scores"]["threat_resource"] == 7
    assert "unobserved_threat_removal" not in target.verdict_json["flags"]
    assert "coordinator_instruction_conflict" not in target.verdict_json["flags"]


@pytest.mark.asyncio
async def test_copied_engine_thwart_option_does_not_falsely_attribute_coordinator_conflict(
    repo,
):
    provenance = {
        "source": "coordinator",
        "prompt": (
            "CURRENT ENGINE PROMPT\n"
            "  1. Thwart — remove 2 threat from the main scheme\n"
            "  2. Attack Rhino — deal 3 damage\n"
            "  3. End turn"
        ),
        "orchestrator_session_id": "orchestrator-1",
        "parent_job_id": "parent-1",
        "child_job_id": "child-1",
    }
    events = [
        marvel_producer_event(
            game_id="g1",
            seq=1,
            state=_normalized_marvel_state(threat=12),
        ),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="choose_game_option",
            arguments={"option_id": "1"},
            reasoning="I choose option 1 and remove 2 threat from the main scheme.",
            prompt_provenance=provenance,
        ),
        marvel_producer_event(
            game_id="g1",
            seq=3,
            state=_normalized_marvel_state(threat=12),
        ),
    ]

    target, judge = await _evaluate_marvel_move(repo, events)

    assert target.verdict_json["overall_score"] == 0
    assert target.verdict_json["scores"]["threat_resource"] == 0
    assert "unobserved_threat_removal" in target.verdict_json["flags"]
    assert "coordinator_instruction_conflict" not in target.verdict_json["flags"]


@pytest.mark.asyncio
async def test_marvel_side_scheme_threat_removal_does_not_penalize_main_scheme(
    repo,
):
    events = [
        marvel_producer_event(
            game_id="g1",
            seq=1,
            state=_normalized_marvel_state(threat=12),
        ),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="choose_game_option",
            reasoning="I removed threat from the side scheme.",
        ),
        marvel_producer_event(
            game_id="g1",
            seq=3,
            state=_normalized_marvel_state(threat=12),
        ),
    ]

    target, _ = await _evaluate_marvel_move(repo, events)

    assert target.verdict_json["overall_score"] == 7
    assert target.verdict_json["scores"]["threat_resource"] == 7
    assert "unobserved_threat_removal" not in target.verdict_json["flags"]


@pytest.mark.asyncio
async def test_marvel_hidden_scheme_state_does_not_invent_threat_change(repo):
    hidden_state = _normalized_marvel_state(threat=12)
    hidden_state["zones"]["sharedMainScheme"][0] = {
        "name": "HIDDEN",
        "tokens": {"threat": 12},
    }
    events = [
        marvel_producer_event(game_id="g1", seq=1, state=hidden_state),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="choose_game_option",
            reasoning="The option is a good play.",
        ),
        marvel_producer_event(game_id="g1", seq=3, state=hidden_state),
    ]

    target, _ = await _evaluate_marvel_move(repo, events)

    assert target.verdict_json["overall_score"] == 7
    assert target.verdict_json["scores"]["threat_resource"] == 7
    assert "unobserved_threat_removal" not in target.verdict_json["flags"]



@pytest.mark.asyncio
async def test_marvel_terminal_win_is_recorded_as_authoritative_evidence(repo):
    events = [
        marvel_producer_event(
            game_id="g1",
            seq=1,
            state=_normalized_marvel_state(threat=12),
        ),
        _marvel_move_event(
            game_id="g1",
            seq=2,
            action="choose_game_option",
            reasoning="The option completes the scenario.",
        ),
        marvel_producer_event(
            game_id="g1",
            seq=3,
            state=_normalized_marvel_state(threat=10, mode="win"),
        ),
    ]

    target, _ = await _evaluate_marvel_move(repo, events)

    assert target.verdict_json["overall_score"] == 7
    assert "terminal_win" in target.verdict_json["flags"]

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
