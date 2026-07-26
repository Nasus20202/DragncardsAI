from __future__ import annotations

import pytest

from eval_service.config import Settings
from eval_service.runtime.requests import (
    GameNotFoundError,
    RequestError,
    RequestService,
)
from eval_service.schemas.api import EvaluationRequestBody, Selection
from tests.unit.conftest import FakeHistoryClient, agent_event, state_event


def _settings():
    return Settings(eval_judge_model="anthropic/claude-x")


def _game(game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2),
        state_event(game_id=game_id, seq=3, round_number=1),
        agent_event(game_id=game_id, seq=4),
        state_event(game_id=game_id, seq=5, round_number=2),
        agent_event(game_id=game_id, seq=6),
        state_event(game_id=game_id, seq=7, round_number=2, status="win"),
    ]


def _service(repository, events):
    return RequestService(
        settings=_settings(),
        repository=repository,
        history=FakeHistoryClient({"g1": events}),
    )


@pytest.mark.asyncio
async def test_only_selected_moves_are_targeted(repository):
    service = _service(repository, _game())
    body = EvaluationRequestBody(scope="move", selection=Selection(seqs=[2, 6]))
    resp = await service.create("g1", body)
    assert resp.created_count == 2
    assert sorted(t.target_seq for t in resp.targets) == [2, 6]
    # seq4 was NOT selected and must not be a target.
    assert 4 not in [t.target_seq for t in resp.targets]


@pytest.mark.asyncio
async def test_non_agent_seqs_are_dropped(repository):
    service = _service(repository, _game())
    # seq1 is a game-service state event, not an agent move.
    body = EvaluationRequestBody(scope="move", selection=Selection(seqs=[1, 2]))
    resp = await service.create("g1", body)
    assert [t.target_seq for t in resp.targets] == [2]


@pytest.mark.asyncio
async def test_whole_game_move_scope_targets_all_agent_moves(repository):
    service = _service(repository, _game())
    body = EvaluationRequestBody(scope="move", selection=Selection(whole_game=True))
    resp = await service.create("g1", body)
    assert sorted(t.target_seq for t in resp.targets) == [2, 4, 6]


@pytest.mark.asyncio
async def test_round_scope_targets_closed_rounds(repository):
    service = _service(repository, _game())
    body = EvaluationRequestBody(scope="round", selection=Selection(whole_game=True))
    resp = await service.create("g1", body)
    # A round request now CASCADES: it claims the move targets each round depends
    # on (scope=move) plus a per-player round roll-up (scope=round). round 1
    # closes at seq4, round 2 (terminal) closes at seq7.
    round_spans = {
        t.target_seq: t.round_span for t in resp.targets if t.scope == "round"
    }
    assert round_spans == {4: [1, 4], 7: [5, 7]}
    move_seqs = sorted(t.target_seq for t in resp.targets if t.scope == "move")
    assert move_seqs == [2, 4, 6]


@pytest.mark.asyncio
async def test_repeat_without_force_not_reevaluated(repository):
    service = _service(repository, _game())
    body = EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    first = await service.create("g1", body)
    assert first.created_count == 1
    second = await service.create("g1", body)
    assert second.created_count == 0
    assert second.skipped_count == 1


@pytest.mark.asyncio
async def test_force_reclaims(repository):
    service = _service(repository, _game())
    body = EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]))
    await service.create("g1", body)
    forced = await service.create(
        "g1",
        EvaluationRequestBody(scope="move", selection=Selection(seqs=[2]), force=True),
    )
    assert forced.created_count == 1


@pytest.mark.asyncio
async def test_game_without_events_404s(repository):
    service = RequestService(
        settings=_settings(),
        repository=repository,
        history=FakeHistoryClient({}),
    )
    with pytest.raises(GameNotFoundError):
        await service.create(
            "missing",
            EvaluationRequestBody(scope="move", selection=Selection(whole_game=True)),
        )


@pytest.mark.asyncio
async def test_selection_matching_nothing_400s(repository):
    service = _service(repository, _game())
    # seqs that are not agent moves -> expands to no targets.
    body = EvaluationRequestBody(scope="move", selection=Selection(seqs=[1, 3, 5]))
    with pytest.raises(RequestError):
        await service.create("g1", body)


@pytest.mark.asyncio
async def test_round_scope_mid_round_seq_resolves_to_containing_round(repository):
    # seq6 is a mid-round agent move inside round 2 (span 5-7); round scope
    # must map it to that round's closing target rather than 400ing.
    service = _service(repository, _game())
    body = EvaluationRequestBody(scope="round", selection=Selection(seqs=[6]))
    resp = await service.create("g1", body)
    # The round roll-up resolves to round 2 (closes at seq7), plus the move
    # targets that round depends on (the cascade).
    round_targets = [t for t in resp.targets if t.scope == "round"]
    assert len(round_targets) == 1
    assert round_targets[0].target_seq == 7  # round 2 closes at seq7
    assert round_targets[0].round_span == [5, 7]
    move_seqs = sorted(t.target_seq for t in resp.targets if t.scope == "move")
    assert move_seqs == [6]


@pytest.mark.asyncio
async def test_round_scope_seq_outside_any_round_400s(repository):
    service = _service(repository, _game())
    # seq 999 is outside every detected round span.
    body = EvaluationRequestBody(scope="round", selection=Selection(seqs=[999]))
    with pytest.raises(RequestError):
        await service.create("g1", body)


@pytest.mark.asyncio
async def test_over_cap_request_rejected(repository):
    service = RequestService(
        settings=Settings(
            eval_judge_model="anthropic/claude-x",
            eval_max_targets_per_request=2,
        ),
        repository=repository,
        history=FakeHistoryClient({"g1": _game()}),
    )
    # whole_game move scope expands to 3 agent moves (seq 2,4,6) > cap of 2.
    body = EvaluationRequestBody(scope="move", selection=Selection(whole_game=True))
    with pytest.raises(RequestError) as excinfo:
        await service.create("g1", body)
    assert "per-request limit" in str(excinfo.value)


@pytest.mark.asyncio
async def test_within_cap_request_passes(repository):
    service = RequestService(
        settings=Settings(
            eval_judge_model="anthropic/claude-x",
            eval_max_targets_per_request=3,
        ),
        repository=repository,
        history=FakeHistoryClient({"g1": _game()}),
    )
    body = EvaluationRequestBody(scope="move", selection=Selection(whole_game=True))
    resp = await service.create("g1", body)
    assert resp.created_count == 3
