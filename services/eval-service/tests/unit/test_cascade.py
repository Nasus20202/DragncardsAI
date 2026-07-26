from __future__ import annotations

import pytest

from eval_service.config import Settings
from eval_service.runtime.requests import RequestService
from eval_service.schemas.api import EvaluationRequestBody, Selection
from tests.unit.conftest import FakeHistoryClient, agent_event, make_event


def _settings():
    return Settings(eval_judge_model="anthropic/claude-x")


def _mp_state(*, seq, round_number, num_players, first_player, status="in progress"):
    player_data = {f"player{i}": {"alias": f"p{i}"} for i in range(1, num_players + 1)}
    return make_event(
        game_id="g1",
        seq=seq,
        actor="game-service",
        event_type="game_state",
        payload={
            "state": {
                "game": {
                    "roundNumber": round_number,
                    "numPlayers": num_players,
                    "firstPlayer": first_player,
                    "playerData": player_data,
                }
            },
            "status": status,
        },
    )


def _two_player_game():
    # Round 1: seqs 2,3 (player1, player2). Round 2: seqs 6,7 (player1, player2).
    return [
        _mp_state(seq=1, round_number=1, num_players=2, first_player="player1"),
        agent_event(game_id="g1", seq=2),
        agent_event(game_id="g1", seq=3),
        _mp_state(seq=4, round_number=1, num_players=2, first_player="player1"),
        _mp_state(seq=5, round_number=2, num_players=2, first_player="player1"),
        agent_event(game_id="g1", seq=6),
        agent_event(game_id="g1", seq=7),
        _mp_state(
            seq=8, round_number=2, num_players=2, first_player="player1", status="win"
        ),
    ]


def _service(repository, events):
    return RequestService(
        settings=_settings(),
        repository=repository,
        history=FakeHistoryClient({"g1": events}),
    )


@pytest.mark.asyncio
async def test_game_request_fans_out_to_moves_rounds_and_game(repository):
    service = _service(repository, _two_player_game())
    body = EvaluationRequestBody(scope="game", selection=Selection(whole_game=True))
    resp = await service.create("g1", body)

    by_scope: dict[str, list] = {"move": [], "round": [], "game": []}
    for t in resp.targets:
        by_scope[t.scope].append(t)

    # Every agent move is a target.
    assert sorted(t.target_seq for t in by_scope["move"]) == [2, 3, 6, 7]
    # One round roll-up PER PLAYER per round (2 rounds x 2 players = 4).
    assert len(by_scope["round"]) == 4
    round_players = sorted((t.target_seq, t.player) for t in by_scope["round"])
    assert round_players == [
        (4, "player1"),
        (4, "player2"),
        (8, "player1"),
        (8, "player2"),
    ]
    # One game roll-up per player.
    game_players = sorted(t.player for t in by_scope["game"])
    assert game_players == ["player1", "player2"]
    assert all(t.round_span == [1, 8] for t in by_scope["game"])


@pytest.mark.asyncio
async def test_per_player_round_targets_for_multiplayer_span(repository):
    service = _service(repository, _two_player_game())
    body = EvaluationRequestBody(scope="round", selection=Selection(rounds=[1]))
    resp = await service.create("g1", body)

    round_targets = sorted(
        (t.player, t.target_seq) for t in resp.targets if t.scope == "round"
    )
    assert round_targets == [("player1", 4), ("player2", 4)]
    # Moves of round 1 (seqs 2,3) are also claimed, attributed per player.
    move_players = sorted(
        (t.target_seq, t.player) for t in resp.targets if t.scope == "move"
    )
    assert move_players == [(2, "player1"), (3, "player2")]


@pytest.mark.asyncio
async def test_already_graded_children_are_reused(repository):
    service = _service(repository, _two_player_game())
    body = EvaluationRequestBody(scope="game", selection=Selection(whole_game=True))
    first = await service.create("g1", body)
    assert first.created_count > 0
    # A repeat (no force) re-claims nothing: every target already exists.
    second = await service.create("g1", body)
    assert second.created_count == 0
    assert second.skipped_count == len(second.targets)


@pytest.mark.asyncio
async def test_round_scope_single_player_one_round_target(repository):
    # Single-player game: each round produces exactly one (player1) roll-up.
    events = [
        _mp_state(seq=1, round_number=1, num_players=1, first_player="player1"),
        agent_event(game_id="g1", seq=2),
        _mp_state(
            seq=3, round_number=1, num_players=1, first_player="player1", status="win"
        ),
    ]
    service = _service(repository, events)
    body = EvaluationRequestBody(scope="round", selection=Selection(whole_game=True))
    resp = await service.create("g1", body)
    round_targets = [t for t in resp.targets if t.scope == "round"]
    assert len(round_targets) == 1
    assert round_targets[0].player == "player1"
