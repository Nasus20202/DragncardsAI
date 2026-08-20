from __future__ import annotations

import pytest

from eval_service.judge.assembly import round_of_play
from eval_service.judge.rounds import (
    neighbour_events,
    round_label,
    round_span_containing,
)
from eval_service.runtime.rounds import RoundsService
from eval_service.runtime.requests import GameNotFoundError
from eval_service.schemas.history import PLATFORM_MARVEL_LCG
from tests.unit.conftest import FakeHistoryClient, agent_event, make_event, state_event


def test_round_label_names_the_round_of_play():
    # `round_label` takes the round OF PLAY, which is what detect_round_boundaries
    # already reports. DragnCards' raw roundNumber counts COMPLETED rounds, so it
    # reads 0 throughout the first round of play -- labelling it directly would
    # name every round one too low.
    assert round_label(round_of_play(0)) == "Round 1"
    assert round_label(round_of_play(7)) == "Round 8"
    assert round_label(None) == "Unknown round"


def test_round_span_containing_finds_the_enclosing_boundary():
    boundaries = [(1, 1, 10), (2, 11, 20)]
    assert round_span_containing(boundaries, 1) == (1, 1, 10)
    assert round_span_containing(boundaries, 10) == (1, 1, 10)
    assert round_span_containing(boundaries, 11) == (2, 11, 20)
    assert round_span_containing(boundaries, 99) is None
    assert round_span_containing([], 5) is None


def _span_game():
    return [
        state_event(game_id="g1", seq=1, round_number=0),
        agent_event(game_id="g1", seq=2),
        agent_event(game_id="g1", seq=3),
        agent_event(game_id="g1", seq=4),
        state_event(game_id="g1", seq=5, round_number=1),
        agent_event(game_id="g1", seq=6),
    ]


def test_neighbour_events_confined_to_the_span():
    events = _span_game()
    before = neighbour_events(events, 3, direction="before", limit=10, span=(1, 4))
    after = neighbour_events(events, 3, direction="after", limit=10, span=(1, 4))
    assert [e.seq for e in before] == [2]
    # seq 6 is outside the span and must not leak in.
    assert [e.seq for e in after] == [4]


def test_neighbour_events_without_a_span_spans_the_timeline():
    events = _span_game()
    after = neighbour_events(events, 3, direction="after", limit=10, span=None)
    assert [e.seq for e in after] == [4, 6]


def test_neighbour_events_limit_keeps_the_nearest_and_zero_selects_none():
    events = _span_game()
    assert [
        e.seq for e in neighbour_events(events, 4, direction="before", limit=1)
    ] == [3]
    assert neighbour_events(events, 4, direction="before", limit=0) == []


def test_neighbour_events_ignores_non_agent_actors():
    events = _span_game()
    before = neighbour_events(events, 4, direction="before", limit=10)
    assert all(e.actor == "agent" for e in before)


@pytest.mark.asyncio
async def test_rounds_service_lists_labelled_spans_with_move_counts():
    events = _span_game()
    service = RoundsService(history=FakeHistoryClient({"g1": events}))
    response = await service.list_rounds("g1")

    assert response.game_id == "g1"
    first = response.rounds[0]
    # round_number is the round OF PLAY, which is exactly what selection.rounds
    # accepts, so a client echoes it back untranslated.
    assert first.round_number == 1
    assert first.label == "Round 1"
    # The round closes AT the seq-5 state event that first reported the new round,
    # so its span covers the three agent moves at seqs 2-4.
    assert (first.from_seq, first.to_seq) == (1, 5)
    assert first.move_count == 3
    assert first.players == ["player1"]


@pytest.mark.asyncio
async def test_rounds_service_reports_a_round_with_no_agent_moves():
    events = [
        state_event(game_id="g2", seq=1, round_number=0),
        state_event(game_id="g2", seq=2, round_number=1),
        state_event(game_id="g2", seq=3, round_number=1, status="win"),
    ]
    service = RoundsService(history=FakeHistoryClient({"g2": events}))
    rounds = (await service.list_rounds("g2")).rounds
    assert rounds[0].move_count == 0
    assert rounds[0].players == []


@pytest.mark.asyncio
async def test_rounds_service_404s_an_unrecorded_game():
    # "This game does not exist" must not be reported as "this game has no rounds".
    service = RoundsService(history=FakeHistoryClient({}))
    with pytest.raises(GameNotFoundError):
        await service.list_rounds("nope")


@pytest.mark.asyncio
async def test_rounds_service_tolerates_a_raw_nested_state():
    # Recorded state comes in two shapes; a raw DragnCards state nests roundNumber
    # under ``state.game``.
    events = [
        make_event(
            game_id="g3",
            seq=1,
            actor="game-service",
            event_type="game_state",
            payload={"state": {"game": {"roundNumber": 2}}},
        ),
        agent_event(game_id="g3", seq=2),
        make_event(
            game_id="g3",
            seq=3,
            actor="game-service",
            event_type="game_state",
            payload={"state": {"game": {"roundNumber": 3}}, "status": "win"},
        ),
    ]
    service = RoundsService(history=FakeHistoryClient({"g3": events}))
    rounds = (await service.list_rounds("g3")).rounds
    # raw roundNumber 2 -> round of play 3. The terminal seq-3 event is the same
    # event that closed the round, so it does not also open an empty final one.
    assert [r.label for r in rounds] == ["Round 3"]


@pytest.mark.asyncio
async def test_rounds_service_lists_marvel_round_id_as_round_of_play():
    def state(seq: int, round_id: int, *, status: str = "in progress"):
        return make_event(
            game_id="marvel-list",
            seq=seq,
            actor="game-service",
            event_type="game_state",
            payload={"state": {"round_id": round_id}, "status": status},
        ).model_copy(update={"platform": PLATFORM_MARVEL_LCG})

    move = agent_event(game_id="marvel-list", seq=2).model_copy(
        update={"platform": PLATFORM_MARVEL_LCG}
    )
    service = RoundsService(
        history=FakeHistoryClient(
            {"marvel-list": [state(1, 1), move, state(3, 2, status="win")]}
        )
    )

    rounds = (await service.list_rounds("marvel-list", PLATFORM_MARVEL_LCG)).rounds
    assert [(item.round_number, item.label) for item in rounds] == [(1, "Round 1")]


@pytest.mark.asyncio
async def test_rounds_service_does_not_list_marvel_setup_as_a_selectable_round():
    def state(seq: int, play_round: int, *, status: str = "in progress"):
        return make_event(
            game_id="marvel-setup-list",
            seq=seq,
            actor="game-service",
            event_type="game_state",
            payload={"state": {"playRound": play_round}, "status": status},
        ).model_copy(update={"platform": PLATFORM_MARVEL_LCG})

    events = [
        state(1, 0),
        state(2, 1),
        agent_event(game_id="marvel-setup-list", seq=3).model_copy(
            update={"platform": PLATFORM_MARVEL_LCG}
        ),
        state(4, 2),
        agent_event(game_id="marvel-setup-list", seq=5).model_copy(
            update={"platform": PLATFORM_MARVEL_LCG}
        ),
        state(6, 2, status="win"),
    ]
    service = RoundsService(history=FakeHistoryClient({"marvel-setup-list": events}))

    rounds = (
        await service.list_rounds("marvel-setup-list", PLATFORM_MARVEL_LCG)
    ).rounds

    assert [(item.round_number, item.label) for item in rounds] == [
        (1, "Round 1"),
        (2, "Round 2"),
    ]


@pytest.mark.asyncio
async def test_rounds_service_lists_no_rounds_for_setup_only_history():
    def state(seq: int, *, status: str):
        return make_event(
            game_id="marvel-setup-only-list",
            seq=seq,
            actor="game-service",
            event_type="game_state",
            payload={"state": {"playRound": 0}, "status": status},
        ).model_copy(update={"platform": PLATFORM_MARVEL_LCG})

    service = RoundsService(
        history=FakeHistoryClient(
            {
                "marvel-setup-only-list": [
                    state(1, status="in progress"),
                    state(2, status="win"),
                ]
            }
        )
    )

    assert (
        await service.list_rounds("marvel-setup-only-list", PLATFORM_MARVEL_LCG)
    ).rounds == []
