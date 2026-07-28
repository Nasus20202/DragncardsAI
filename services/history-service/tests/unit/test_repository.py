from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from .conftest import make_envelope


@pytest.mark.asyncio
async def test_seq_is_gap_free_and_increasing(repository):
    for offset in range(5):
        result = await repository.commit_event(
            make_envelope("g1", producer_offset=offset)
        )
        assert result.inserted
        assert result.event.seq == offset + 1
    assert await repository.get_latest_seq("g1") == 5


@pytest.mark.asyncio
async def test_independent_sequences_across_games(repository):
    await repository.commit_event(make_envelope("g1", producer_offset=0))
    await repository.commit_event(make_envelope("g2", producer_offset=0))
    await repository.commit_event(make_envelope("g1", producer_offset=1))
    await repository.commit_event(make_envelope("g2", producer_offset=1))
    g1 = await repository.list_events("g1")
    g2 = await repository.list_events("g2")
    assert [e.seq for e in g1] == [1, 2]
    assert [e.seq for e in g2] == [1, 2]


@pytest.mark.asyncio
async def test_duplicate_stored_once_without_consuming_seq(repository):
    first = await repository.commit_event(make_envelope("g1", producer_offset=0))
    dup = await repository.commit_event(make_envelope("g1", producer_offset=0))
    after = await repository.commit_event(make_envelope("g1", producer_offset=1))

    assert first.inserted is True
    assert dup.inserted is False
    assert dup.event.seq == first.event.seq == 1
    # The duplicate did NOT consume a seq; the next genuine event is 2.
    assert after.event.seq == 2
    assert len(await repository.list_events("g1")) == 2


@pytest.mark.asyncio
async def test_out_of_order_delivery_ordered_by_commit(repository):
    now = datetime.now(timezone.utc)
    # occurred_at later but committed first -> still seq 1.
    await repository.commit_event(
        make_envelope("g1", producer_offset=0, occurred_at=now + timedelta(minutes=5))
    )
    await repository.commit_event(
        make_envelope("g1", producer_offset=1, occurred_at=now)
    )
    events = await repository.list_events("g1")
    assert [e.seq for e in events] == [1, 2]
    assert events[0].producer_offset == 0


@pytest.mark.asyncio
async def test_list_events_paging(repository):
    for offset in range(10):
        await repository.commit_event(make_envelope("g1", producer_offset=offset))
    page1 = await repository.list_events("g1", after_seq=0, limit=4)
    assert [e.seq for e in page1] == [1, 2, 3, 4]
    page2 = await repository.list_events("g1", after_seq=4, limit=4)
    assert [e.seq for e in page2] == [5, 6, 7, 8]


@pytest.mark.asyncio
async def test_unknown_game_returns_empty(repository):
    assert await repository.list_events("missing") == []
    assert await repository.list_snapshots("missing") == []
    assert await repository.get_latest_seq("missing") is None


@pytest.mark.asyncio
async def test_range_reads_exclusive_low_inclusive_high(repository):
    for offset in range(5):
        await repository.commit_event(make_envelope("g1", producer_offset=offset))
    events = await repository.get_events_in_range(
        "g1", low_exclusive=2, high_inclusive=4
    )
    assert [e.seq for e in events] == [3, 4]


@pytest.mark.asyncio
async def test_snapshot_write_and_read(repository):
    for offset in range(3):
        await repository.commit_event(make_envelope("g1", producer_offset=offset))
    await repository.write_snapshot("g1", 2, {"schema_version": 1, "game": {"a": 1}})
    snapshots = await repository.list_snapshots("g1")
    assert len(snapshots) == 1
    assert snapshots[0].snapshot_at_seq == 2
    assert snapshots[0].snapshot["game"]["a"] == 1

    nearest = await repository.get_latest_snapshot_at_or_before("g1", 3)
    assert nearest is not None and nearest.snapshot_at_seq == 2
    assert await repository.get_latest_snapshot_at_or_before("g1", 1) is None


@pytest.mark.asyncio
async def test_latest_agent_event_lookup(repository):
    await repository.commit_event(
        make_envelope("g1", actor="game-service", producer_offset=0)
    )
    await repository.commit_event(make_envelope("g1", actor="agent", producer_offset=1))
    await repository.commit_event(
        make_envelope("g1", actor="game-service", producer_offset=2)
    )
    await repository.commit_event(make_envelope("g1", actor="agent", producer_offset=3))

    latest = await repository.get_latest_agent_event_at_or_before("g1", 3)
    assert latest is not None and latest.seq == 2 and latest.actor == "agent"
    latest_all = await repository.get_latest_agent_event_at_or_before("g1", 4)
    assert latest_all is not None and latest_all.seq == 4


@pytest.mark.asyncio
async def test_list_games_empty(repository):
    assert await repository.list_games() == []


@pytest.mark.asyncio
async def test_list_games_counts_and_ordering(repository):
    # g1 recorded first, then g2 — g2 has the most recent activity.
    await repository.commit_event(make_envelope("g1", producer_offset=0))
    await repository.commit_event(make_envelope("g1", producer_offset=1))
    await repository.commit_event(make_envelope("g2", producer_offset=0))

    games = await repository.list_games()
    by_id = {summary.game_id: summary for summary in games}
    assert by_id["g1"].event_count == 2
    assert by_id["g2"].event_count == 1
    # first/last bound the recorded window for each game.
    assert by_id["g1"].first_recorded_at <= by_id["g1"].last_recorded_at
    # Ordered by last_recorded_at DESC: g2 (most recent) precedes g1.
    assert [summary.game_id for summary in games] == ["g2", "g1"]


@pytest.mark.asyncio
async def test_delete_game_history_removes_events_and_snapshots(repository):
    for offset in range(3):
        await repository.commit_event(make_envelope("g1", producer_offset=offset))
    await repository.write_snapshot("g1", 2, {"schema_version": 1, "game": {}})
    # A second game must be untouched.
    await repository.commit_event(make_envelope("g2", producer_offset=0))

    result = await repository.delete_game_history("g1")
    assert result.game_id == "g1"
    assert result.deleted_events == 3
    assert result.deleted_snapshots == 1

    assert await repository.list_events("g1") == []
    assert await repository.list_snapshots("g1") == []
    assert {summary.game_id for summary in await repository.list_games()} == {"g2"}


@pytest.mark.asyncio
async def test_delete_absent_game_is_idempotent(repository):
    result = await repository.delete_game_history("missing")
    assert result.deleted_events == 0
    assert result.deleted_snapshots == 0


@pytest.mark.asyncio
async def test_evaluation_event_player_is_stored_and_returned(repository):
    # A per-player evaluation verdict round-trips its ``player`` payload key.
    await repository.commit_event(
        make_envelope(
            "g1",
            actor="evaluator",
            event_type="evaluation",
            producer_offset="eval-1",
            payload={
                "scope": "round",
                "target_seq": 4,
                "player": "player2",
                "overall_score": 8,
            },
        )
    )
    events = await repository.list_events("g1")
    assert len(events) == 1
    assert events[0].payload["player"] == "player2"
    assert events[0].payload["scope"] == "round"


@pytest.mark.asyncio
async def test_evaluation_event_without_player_round_trips(repository):
    # Backward compatible: an evaluation verdict with no ``player`` is stored
    # and returned unchanged.
    await repository.commit_event(
        make_envelope(
            "g1",
            actor="evaluator",
            event_type="evaluation",
            producer_offset="eval-legacy",
            payload={"scope": "move", "target_seq": 2, "overall_score": 5},
        )
    )
    events = await repository.list_events("g1")
    assert len(events) == 1
    assert "player" not in events[0].payload


# -- timeline summaries -----------------------------------------------------


def _state_payload(round_number: int, step_id: str, *, cards: int = 3) -> dict:
    """A ``game-service`` payload shaped like a real recording, in miniature."""
    return {
        "state": {
            "deltas": [{"i": i} for i in range(cards)],
            "game": {
                "roundNumber": round_number,
                "stepId": step_id,
                "mode": "in progress",
                "cardById": {f"card-{i}": {"id": f"card-{i}"} for i in range(cards)},
            },
        },
        "state_digest": "abc123",
        "status": "in progress",
        "action_path": "actions",
        "action_args": {"type": "move_card"},
    }


@pytest.mark.asyncio
async def test_summary_omits_state_bulk_but_keeps_round_and_step(repository):
    await repository.commit_event(
        make_envelope("g1", producer_offset=0, payload=_state_payload(2, "0.1"))
    )
    (summary,) = await repository.list_event_summaries("g1")
    # The round/step projection survives, the bulk does not.
    assert summary.payload["state"] == {"game": {"roundNumber": 2, "stepId": "0.1"}}
    assert "cardById" not in summary.payload["state"]["game"]
    assert "deltas" not in summary.payload["state"]
    # Everything else in the payload is carried through verbatim.
    assert summary.payload["status"] == "in progress"
    assert summary.payload["state_digest"] == "abc123"
    assert summary.payload["action_args"] == {"type": "move_card"}


@pytest.mark.asyncio
async def test_summary_step_id_stays_a_dotted_string(repository):
    """``0.0`` and ``0.1`` are step *ids*, not numbers; they must not become floats."""
    for offset, step in enumerate(("0.0", "0.1", "1.1", "2.5")):
        await repository.commit_event(
            make_envelope("g1", producer_offset=offset, payload=_state_payload(0, step))
        )
    summaries = await repository.list_event_summaries("g1")
    steps = [s.payload["state"]["game"]["stepId"] for s in summaries]
    assert steps == ["0.0", "0.1", "1.1", "2.5"]


@pytest.mark.asyncio
async def test_summary_keeps_round_zero_distinct_from_missing(repository):
    """Round 0 is the whole first round of play, so 0 must not read as absent."""
    await repository.commit_event(
        make_envelope("g1", producer_offset=0, payload=_state_payload(0, "1.1"))
    )
    (summary,) = await repository.list_event_summaries("g1")
    assert summary.payload["state"]["game"]["roundNumber"] == 0


@pytest.mark.asyncio
async def test_summary_omits_agent_conversation_but_keeps_the_decision(repository):
    await repository.commit_event(
        make_envelope(
            "g1",
            actor="agent",
            producer_offset=0,
            payload={
                "intended_action": "move_card",
                "reasoning": "it blocks the villain",
                "arguments": {"card_id": "card-1"},
                "conversation_context": [{"role": "user", "content": "x" * 5000}],
            },
        )
    )
    (summary,) = await repository.list_event_summaries("g1")
    assert "conversation_context" not in summary.payload
    assert summary.payload["intended_action"] == "move_card"
    assert summary.payload["reasoning"] == "it blocks the villain"
    assert summary.payload["arguments"] == {"card_id": "card-1"}
    # No game state was observed, so nothing is projected under ``state``.
    assert "state" not in summary.payload


@pytest.mark.asyncio
async def test_summary_paging_follows_the_same_cursor_as_the_events_read(repository):
    for offset in range(10):
        await repository.commit_event(
            make_envelope(
                "g1", producer_offset=offset, payload=_state_payload(0, "1.1")
            )
        )
    page1 = await repository.list_event_summaries("g1", after_seq=0, limit=4)
    assert [e.seq for e in page1] == [1, 2, 3, 4]
    page2 = await repository.list_event_summaries("g1", after_seq=4, limit=4)
    assert [e.seq for e in page2] == [5, 6, 7, 8]
    page3 = await repository.list_event_summaries("g1", after_seq=8, limit=4)
    assert [e.seq for e in page3] == [9, 10]


@pytest.mark.asyncio
async def test_summary_carries_the_envelope_identity_fields(repository):
    await repository.commit_event(
        make_envelope("g1", producer_offset=7, payload=_state_payload(1, "2.1"))
    )
    (summary,) = await repository.list_event_summaries("g1")
    (full,) = await repository.list_events("g1")
    assert summary.event_id == full.event_id
    assert summary.game_id == full.game_id == "g1"
    assert summary.actor == full.actor
    assert summary.event_type == full.event_type
    assert summary.envelope_version == full.envelope_version
    assert summary.idempotency_key == full.idempotency_key
    assert summary.producer_offset == full.producer_offset == 7
    assert summary.occurred_at == full.occurred_at


@pytest.mark.asyncio
async def test_summary_of_unknown_game_is_empty(repository):
    assert await repository.list_event_summaries("missing") == []
