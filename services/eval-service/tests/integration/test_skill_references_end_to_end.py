"""A selected skill reference survives the whole request -> worker -> judge path.

The unit tests pin the resolver and the prompt separately. This pins the join:
that the reference selection is validated at request time, persisted on the
target row, re-resolved by the worker in a fresh evaluator, and present in the
messages the judge client is actually called with. Before DRA-41 nothing in this
path could read a reference file at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval_service.config import Settings
from eval_service.judge.config import SkillResolver, resolve_judge_config
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.requests import RequestError, RequestService
from eval_service.runtime.worker import EvaluationWorker
from eval_service.schemas.api import EvaluationRequestBody, JudgeConfig, Selection
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)

pytestmark = pytest.mark.postgres


def _recorded_game(game_id="gref"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2, action="play_a"),
        state_event(game_id=game_id, seq=3, round_number=2, status="win"),
    ]


def _skill_root(tmp_path: Path) -> Path:
    root = tmp_path / "skills"
    skill = root / "rules"
    (skill / "resources").mkdir(parents=True)
    (skill / "SKILL.md").write_text("SKILLBODY-AAA", encoding="utf-8")
    (skill / "resources" / "errata.md").write_text("ERRATABODY-ZZZ", encoding="utf-8")
    return root


def _settings(root: Path, **overrides) -> Settings:
    base = dict(
        eval_judge_model="anthropic/claude-x",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
        skill_roots=str(root),
    )
    base.update(overrides)
    return Settings(**base)


def _wire(postgres_repository, history, judge, settings):
    resolver = SkillResolver(settings.skill_root_paths)
    evaluator = Evaluator(
        settings=settings,
        repository=postgres_repository,
        history=history,
        judge=judge,
        skill_resolver=resolver,
    )
    request_service = RequestService(
        settings=settings,
        repository=postgres_repository,
        history=history,
        skill_resolver=resolver,
    )
    worker = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=evaluator,
    )
    return request_service, worker


@pytest.mark.asyncio
async def test_a_selected_reference_reaches_the_judge_call(
    postgres_repository, tmp_path
):
    root = _skill_root(tmp_path)
    history = FakeHistoryClient({"gref": _recorded_game()})
    judge = StubJudgeClient()
    settings = _settings(root)
    request_service, worker = _wire(postgres_repository, history, judge, settings)

    response = await request_service.create(
        "gref",
        EvaluationRequestBody(
            scope="move",
            selection=Selection(seqs=[2]),
            judge=JudgeConfig(
                skills=["rules"],
                skill_references=["rules/resources/errata.md"],
            ),
        ),
    )
    assert response.created_count == 1

    await worker.drain_once()

    targets = await postgres_repository.list_targets_for_request(response.request_id)
    assert [t.status for t in targets] == ["completed"]

    system = judge.calls[0]["messages"][0]["content"]
    assert "SKILLBODY-AAA" in system
    assert "ERRATABODY-ZZZ" in system
    assert "### Reference: resources/errata.md" in system


@pytest.mark.asyncio
async def test_a_reference_outside_the_skill_is_refused_before_any_target(
    postgres_repository, tmp_path
):
    root = _skill_root(tmp_path)
    (tmp_path / "secret.md").write_text("OUTSIDE-SECRET", encoding="utf-8")
    history = FakeHistoryClient({"gref": _recorded_game()})
    judge = StubJudgeClient()
    settings = _settings(root)
    request_service, worker = _wire(postgres_repository, history, judge, settings)

    with pytest.raises(RequestError):
        await request_service.create(
            "gref",
            EvaluationRequestBody(
                scope="move",
                selection=Selection(seqs=[2]),
                judge=JudgeConfig(skill_references=["rules/../../secret.md"]),
            ),
        )

    # Nothing was enqueued and no judge call was spent.
    await worker.drain_once()
    assert judge.calls == []
    assert history.written == []


@pytest.mark.asyncio
async def test_a_reference_selection_is_persisted_on_the_target(
    postgres_repository, tmp_path
):
    root = _skill_root(tmp_path)
    history = FakeHistoryClient({"gref": _recorded_game()})
    judge = StubJudgeClient()
    settings = _settings(root)
    request_service, _ = _wire(postgres_repository, history, judge, settings)

    response = await request_service.create(
        "gref",
        EvaluationRequestBody(
            scope="move",
            selection=Selection(seqs=[2]),
            judge=JudgeConfig(skill_references=["rules/resources/errata.md"]),
        ),
    )

    targets = await postgres_repository.list_targets_for_request(response.request_id)
    stored = targets[0].judge_config_json
    assert stored["skill_references"] == ["rules/resources/errata.md"]


def test_a_reference_free_request_stores_no_reference_key(tmp_path):
    """The persisted config -- and so the idempotency key -- must not move."""
    root = _skill_root(tmp_path)
    settings = _settings(root)
    resolver = SkillResolver(settings.skill_root_paths)
    resolved = resolve_judge_config(settings, JudgeConfig(skills=["rules"]), resolver)
    assert "skill_references" not in resolved.to_json()
