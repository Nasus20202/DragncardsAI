from __future__ import annotations

import pytest

from eval_service.config import Settings
from eval_service.runtime.evaluator import Evaluator
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    make_event,
)


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        evaluator_version="eval-1",
        eval_max_attempts=2,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


def _mp_state(*, seq, round_number, status="in progress"):
    return make_event(
        game_id="g1",
        seq=seq,
        actor="game-service",
        event_type="game_state",
        payload={
            "state": {
                "game": {
                    "roundNumber": round_number,
                    "numPlayers": 2,
                    "firstPlayer": "player1",
                    "playerData": {
                        "player1": {"alias": "p1"},
                        "player2": {"alias": "p2"},
                    },
                }
            },
            "status": status,
        },
    )


def _move_verdict_event(*, seq, player, overall, rationale):
    return make_event(
        game_id="g1",
        seq=seq,
        actor="evaluator",
        event_type="evaluation",
        payload={
            "scope": "move",
            "target_seq": seq,
            "player": player,
            "overall_score": overall,
            "rationale": rationale,
            "scores": {
                "rules_legality": overall,
                "strategic_quality": overall,
                "tempo_efficiency": overall,
                "threat_resource": overall,
            },
        },
    )


def _round1_events_with_move_verdicts():
    # Round 1 closes at seq4; moves seq2 (player1), seq3 (player2) already graded.
    return [
        _mp_state(seq=1, round_number=1),
        agent_event(game_id="g1", seq=2),
        agent_event(game_id="g1", seq=3),
        _mp_state(seq=4, round_number=1, status="win"),
        _move_verdict_event(seq=2, player="player1", overall=9, rationale="P1-move"),
        _move_verdict_event(seq=3, player="player2", overall=3, rationale="P2-move"),
    ]


async def _claim_round(repository, *, player, closing_seq=4):
    await repository.create_request(
        request_id=f"r-{player}",
        game_id="g1",
        scope="round",
        selection={"rounds": [1]},
        force=False,
    )
    await repository.claim_target(
        request_id=f"r-{player}",
        game_id="g1",
        target_seq=closing_seq,
        scope="round",
        round_span=(1, closing_seq),
        force=False,
        player=player,
    )
    claimed = await repository.claim_pending_targets()
    return next(c.id for c in claimed if c.player == player)


@pytest.mark.asyncio
async def test_round_verdict_for_player_considers_only_that_players_moves(repository):
    events = _round1_events_with_move_verdicts()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_round(repository, player="player1")

    await evaluator.evaluate_target(
        target_id=target_id,
        game_id="g1",
        target_seq=4,
        scope="round",
        events=events,
        player="player1",
    )

    row = await repository.get_target_by_id(target_id)
    assert row.status == "completed"
    # The written-back verdict carries the player.
    assert history.written
    _, envelope = history.written[-1]
    assert envelope["payload"]["player"] == "player1"
    assert envelope["payload"]["scope"] == "round"

    # The judge prompt included player1's move verdict as context, not player2's.
    prompt = judge.calls[-1]["messages"][-1]["content"]
    assert "P1-move" in prompt
    assert "P2-move" not in prompt


@pytest.mark.asyncio
async def test_round_verdict_records_the_round_of_play_beside_its_seq_span(repository):
    # The fixture's states report raw ``roundNumber`` 1 over seqs 1-4, so the round
    # of PLAY is 2 while the seq span is [1, 4]. The verdict must carry both, and
    # they must not be confused: a consumer that reads the span as round numbers
    # calls this "Rounds 1-4" (DRA-25).
    events = _round1_events_with_move_verdicts()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    target_id = await _claim_round(repository, player="player1")

    await evaluator.evaluate_target(
        target_id=target_id,
        game_id="g1",
        target_seq=4,
        scope="round",
        events=events,
        player="player1",
    )

    _, envelope = history.written[-1]
    payload = envelope["payload"]
    assert payload["scope"] == "round"
    assert payload["round_span"] == [1, 4]
    assert payload["round_number"] == 2
    # And it is stored on the bookkeeping row's verdict too.
    row = await repository.get_target_by_id(target_id)
    assert row.verdict_json["round_number"] == 2


@pytest.mark.asyncio
async def test_round_rollup_defers_while_a_move_child_is_pending(repository):
    # A round roll-up must NOT be produced while a child move target is still
    # in flight: it is re-deferred to ``pending`` instead.
    events = _round1_events_with_move_verdicts()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )
    # Seed a still-pending move child target in the round's span.
    await repository.create_request(
        request_id="r-moves",
        game_id="g1",
        scope="move",
        selection={"seqs": [2]},
        force=False,
    )
    await repository.claim_target(
        request_id="r-moves",
        game_id="g1",
        target_seq=2,
        scope="move",
        round_span=None,
        force=False,
        player="player1",
    )  # left pending (never claimed into running)

    target_id = await _claim_round(repository, player="player1")
    await evaluator.evaluate_target(
        target_id=target_id,
        game_id="g1",
        target_seq=4,
        scope="round",
        events=events,
        player="player1",
    )

    # The roll-up was re-deferred, not graded.
    row = await repository.get_target_by_id(target_id)
    assert row.status == "pending"
    assert judge.calls == []
    assert history.written == []


@pytest.mark.asyncio
async def test_per_player_round_verdicts_are_distinct(repository):
    events = _round1_events_with_move_verdicts()
    history = FakeHistoryClient({"g1": events})
    judge = StubJudgeClient()
    evaluator = Evaluator(
        settings=_settings(), repository=repository, history=history, judge=judge
    )

    p1_id = await _claim_round(repository, player="player1")
    await evaluator.evaluate_target(
        target_id=p1_id,
        game_id="g1",
        target_seq=4,
        scope="round",
        events=events,
        player="player1",
    )
    p2_id = await _claim_round(repository, player="player2")
    await evaluator.evaluate_target(
        target_id=p2_id,
        game_id="g1",
        target_seq=4,
        scope="round",
        events=events,
        player="player2",
    )

    # Two distinct round verdict events were written, one per player, each with
    # its own player attribution and a distinct idempotency key.
    round_writes = [
        e for _, e in history.written if e["payload"].get("scope") == "round"
    ]
    assert len(round_writes) == 2
    players = sorted(e["payload"]["player"] for e in round_writes)
    assert players == ["player1", "player2"]
    keys = {e["idempotency_key"] for e in round_writes}
    assert len(keys) == 2
