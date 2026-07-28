from __future__ import annotations

import pytest

from eval_service.config import Settings
from eval_service.integrations.bifrost import BifrostError
from eval_service.judge.writeback import verdict_idempotency_key
from eval_service.runtime.evaluator import Evaluator, JudgeNotConfiguredError
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


async def _claim_move(repository, seq=2, game_id="g1"):
    await repository.create_request(
        request_id="r1",
        game_id=game_id,
        scope="move",
        selection={"seqs": [seq]},
        force=False,
    )
    await repository.claim_target(
        request_id="r1",
        game_id=game_id,
        target_seq=seq,
        scope="move",
        round_span=None,
        force=False,
    )
    # The worker claims pending targets into ``running`` before the evaluator
    # processes them; simulate that so the evaluator's conditional transitions
    # (which require ``running``) apply.
    claimed = await repository.claim_pending_targets()
    return claimed[0].id


@pytest.mark.asyncio
async def test_successful_move_evaluation_writes_back_then_finalizes(repository):
    events = _events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_move(repository)

    await evaluator.evaluate_target(
        target_id=target_id,
        game_id="g1",
        target_seq=2,
        scope="move",
        events=events,
    )

    row = await repository.get_target_by_id(target_id)
    assert row.status == "completed"
    assert row.verdict_json["overall_score"] == 7
    # Verdict was written back as an evaluator event with the right key. The
    # key folds in the resolved judge config; with no per-request config the
    # evaluator falls back to its default config, so the expected key uses it.
    assert len(history.written) == 1
    game_id, envelope = history.written[0]
    assert envelope["actor"] == "evaluator"
    assert envelope["idempotency_key"] == verdict_idempotency_key(
        "g1", 2, "move", "eval-1", evaluator._default_config()
    )


@pytest.mark.asyncio
async def test_judge_retries_then_succeeds(repository):
    events = _events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient(fail_times=2)  # fails twice, succeeds on 3rd
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_move(repository)
    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )
    row = await repository.get_target_by_id(target_id)
    assert row.status == "completed"
    assert len(judge.calls) == 3


@pytest.mark.asyncio
async def test_failing_judge_skips_target_without_writeback(repository):
    events = _events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient(error=BifrostError("gateway_error", "down", retryable=True))
    evaluator = Evaluator(
        settings=_settings(eval_max_attempts=2),
        repository=repository,
        history=history,
        judge=judge,
    )
    target_id = await _claim_move(repository)
    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )
    row = await repository.get_target_by_id(target_id)
    assert row.status == "skipped"
    assert row.error
    # Nothing written back when the judge never produced a verdict.
    assert history.written == []


@pytest.mark.asyncio
async def test_non_retryable_judge_error_fails_fast(repository):
    events = _events()
    history = FakeHistoryClient({"g1": events})
    # A non-retryable BifrostError (e.g. a 4xx) must NOT burn further attempts.
    judge = StubJudgeClient(
        error=BifrostError("gateway_error", "bad request", retryable=False)
    )
    evaluator = Evaluator(
        settings=_settings(eval_max_attempts=3),
        repository=repository,
        history=history,
        judge=judge,
    )
    target_id = await _claim_move(repository)
    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )
    row = await repository.get_target_by_id(target_id)
    assert row.status == "skipped"
    # Only one judge call despite eval_max_attempts=3 -> failed fast.
    assert len(judge.calls) == 1


@pytest.mark.asyncio
async def test_skip_reason_carries_the_gateway_error(repository):
    """The gateway's own message must reach the target, not a generic "failed".

    A missing dedicated judge key is reported by Bifrost as a definitive 400; if
    that text were swallowed, the operator would see only "judge failed" and have
    no idea the judge key for that provider is not configured.
    """
    events = _events()
    history = FakeHistoryClient({"g1": events})
    message = (
        'no supported key found with name "eval-judge" for provider: openrouter '
        "and model: anthropic/claude-sonnet-4"
    )
    judge = StubJudgeClient(error=BifrostError("gateway_error", message))
    evaluator = Evaluator(
        settings=_settings(eval_judge_model="openrouter/anthropic/claude-sonnet-4"),
        repository=repository,
        history=history,
        judge=judge,
    )
    target_id = await _claim_move(repository)
    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )
    row = await repository.get_target_by_id(target_id)
    assert row.status == "skipped"
    assert message in row.error


@pytest.mark.asyncio
async def test_writeback_failure_marks_skipped(repository):
    events = _events()
    history = FakeHistoryClient({"g1": events})
    history.write_error = RuntimeError("history down")
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_move(repository)
    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )
    row = await repository.get_target_by_id(target_id)
    assert row.status == "skipped"


@pytest.mark.asyncio
async def test_cancel_before_writeback_aborts_write(repository):
    # A cancel that lands AFTER the target was claimed running but BEFORE the
    # verdict write-back must abort the write: no history event, and the
    # cancelled status is left untouched.
    events = _events()
    history = FakeHistoryClient({"g1": events})

    class CancellingJudge(StubJudgeClient):
        """Flips the durable row to ``cancelled`` while the judge call runs,
        mimicking a cancel arriving in the register-after-claim window."""

        def __init__(self, repo, target_id):
            super().__init__()
            self._repo = repo
            self._target_id = target_id

        async def judge(self, *, model, messages, max_tokens, gateway_options=None):
            await self._repo.cancel_request_targets("r1")
            return await super().judge(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                gateway_options=gateway_options,
            )

    target_id = await _claim_move(repository)
    judge = CancellingJudge(repository, target_id)
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )

    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )

    row = await repository.get_target_by_id(target_id)
    # Cancellation stands; the stale verdict was NOT written or finalized.
    assert row.status == "cancelled"
    assert row.verdict_json is None
    assert history.written == []


@pytest.mark.asyncio
async def test_refuses_when_no_judge_model(repository):
    events = _events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(eval_judge_model=""),
        repository=repository,
        history=history,
        judge=judge,
    )
    target_id = await _claim_move(repository)
    with pytest.raises(JudgeNotConfiguredError):
        await evaluator.evaluate_target(
            target_id=target_id,
            game_id="g1",
            target_seq=2,
            scope="move",
            events=events,
        )
    row = await repository.get_target_by_id(target_id)
    assert row.status == "skipped"
    assert judge.calls == []  # never invoked a default model


def _non_strategic_events(action="search_cards_marvel_champions", game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2, action=action),
        state_event(game_id=game_id, seq=3, round_number=1),
    ]


@pytest.mark.asyncio
async def test_non_strategic_move_is_skipped_with_a_reason_and_no_judge_call(
    repository,
):
    # Searching for cards cannot be a wrong decision, so no judge call is spent
    # on it -- and the outcome is recorded as SKIPPED with the reason, so it can
    # never be mistaken for a passing verdict.
    events = _non_strategic_events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_move(repository)

    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )

    row = await repository.get_target_by_id(target_id)
    assert row.status == "skipped"
    assert "non-strategic action" in row.error
    assert "search_cards_marvel_champions" in row.error
    assert "cannot be a wrong play" in row.error
    assert row.verdict_json is None
    assert judge.calls == []
    assert history.written == []


@pytest.mark.asyncio
async def test_taking_a_card_into_hand_is_still_judged(repository):
    # A guard against the dangerous direction: over-skipping degrades evaluation
    # quality silently. Drawing commits game state a player can get wrong, so it
    # must reach the judge no matter how the skip list grows.
    events = _non_strategic_events(action="draw_card")
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_move(repository)

    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )

    row = await repository.get_target_by_id(target_id)
    assert row.status == "completed"
    assert len(judge.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "skip_enabled,expected_status,expected_calls",
    [(True, "skipped", 0), (False, "completed", 1)],
)
async def test_non_strategic_skipping_is_switchable(
    repository, skip_enabled, expected_status, expected_calls
):
    # The SAME non-strategic move under both settings, so the setting is shown to
    # be what decides the outcome.
    events = _non_strategic_events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(eval_skip_non_strategic_moves=skip_enabled),
        repository=repository,
        history=history,
        judge=judge,
    )
    target_id = await _claim_move(repository)

    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=2, scope="move", events=events
    )

    row = await repository.get_target_by_id(target_id)
    assert row.status == expected_status
    assert len(judge.calls) == expected_calls


@pytest.mark.asyncio
async def test_round_rollup_of_only_non_strategic_moves_is_not_skipped(repository):
    # The skip is a MOVE-scope judgement. A round roll-up still runs; it just
    # lists no gradeable moves, and says so, rather than vanishing.
    events = _non_strategic_events()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    await repository.create_request(
        request_id="r-round",
        game_id="g1",
        scope="round",
        selection={"seqs": [3]},
        force=False,
    )
    await repository.claim_target(
        request_id="r-round",
        game_id="g1",
        target_seq=3,
        scope="round",
        round_span=(1, 3),
        force=False,
    )
    claimed = await repository.claim_pending_targets()

    await evaluator.evaluate_target(
        target_id=claimed[0].id,
        game_id="g1",
        target_seq=3,
        scope="round",
        events=events,
    )

    row = await repository.get_target_by_id(claimed[0].id)
    assert row.status == "completed"
    prompt = judge.calls[0]["messages"][1]["content"]
    assert "1 non-strategic action(s) omitted" in prompt


@pytest.mark.asyncio
async def test_move_prompt_carries_the_configured_neighbour_window(repository):
    events = [
        state_event(game_id="g1", seq=1, round_number=1),
        agent_event(game_id="g1", seq=2, action="move_card"),
        agent_event(game_id="g1", seq=3, action="modify_tokens"),
        agent_event(game_id="g1", seq=4, action="exhaust_card"),
        state_event(game_id="g1", seq=5, round_number=1),
    ]
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(
            eval_judge_move_context_before=1, eval_judge_move_context_after=1
        ),
        repository=repository,
        history=history,
        judge=judge,
    )
    target_id = await _claim_move(repository, seq=3)

    await evaluator.evaluate_target(
        target_id=target_id, game_id="g1", target_seq=3, scope="move", events=events
    )

    prompt = judge.calls[0]["messages"][1]["content"]
    assert 'seq 2: action="move_card"' in prompt
    assert 'seq 4: action="exhaust_card"' in prompt
