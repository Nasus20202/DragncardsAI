from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from history_service.schemas.envelope import EventEnvelope


def _envelope(game_id: str, *, actor="game-service", offset=0, event_type="state"):
    return EventEnvelope(
        game_id=game_id,
        actor=actor,
        event_type=event_type,
        payload={"offset": offset},
        occurred_at=datetime.now(timezone.utc),
        idempotency_key=f"{game_id}:{actor}:{offset}",
        producer_offset=offset,
    )


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_gap_free_seq_on_postgres(postgres_repository):
    for offset in range(5):
        result = await postgres_repository.commit_event(_envelope("g1", offset=offset))
        assert result.event.seq == offset + 1
    events = await postgres_repository.list_events("g1")
    assert [e.seq for e in events] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_duplicate_stored_once_on_postgres(postgres_repository):
    first = await postgres_repository.commit_event(_envelope("g1", offset=0))
    dup = await postgres_repository.commit_event(_envelope("g1", offset=0))
    assert first.inserted and not dup.inserted
    assert dup.event.seq == 1
    assert len(await postgres_repository.list_events("g1")) == 1


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_concurrent_commits_preserve_gap_free_seq(postgres_repository):
    """Two concurrent ingesters committing the same game keep one gap-free series.

    The per-game advisory lock serializes seq assignment; the unique constraint
    collapses duplicates. After the storm, seqs are exactly 1..N with no gaps.
    """
    envelopes = [_envelope("g1", offset=i) for i in range(20)]
    # Submit each envelope twice concurrently (at-least-once duplicates).
    tasks = [
        postgres_repository.commit_event(env) for env in envelopes for _ in range(2)
    ]
    await asyncio.gather(*tasks)
    events = await postgres_repository.list_events("g1", limit=1000)
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, 21))  # gap-free, each offset stored once


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_list_games_grouped_on_postgres(postgres_repository):
    await postgres_repository.commit_event(_envelope("g1", offset=0))
    await postgres_repository.commit_event(_envelope("g1", offset=1))
    await postgres_repository.commit_event(_envelope("g2", offset=0))

    games = await postgres_repository.list_games()
    # Ordered by last_recorded_at DESC: g2 recorded after g1.
    assert [summary.game_id for summary in games] == ["g2", "g1"]
    by_id = {summary.game_id: summary for summary in games}
    assert by_id["g1"].event_count == 2
    assert by_id["g2"].event_count == 1
    assert by_id["g1"].first_recorded_at <= by_id["g1"].last_recorded_at


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_delete_game_history_on_postgres(postgres_repository):
    for offset in range(3):
        await postgres_repository.commit_event(_envelope("g1", offset=offset))
    await postgres_repository.write_snapshot("g1", 2, {"schema_version": 1, "game": {}})
    await postgres_repository.commit_event(_envelope("g2", offset=0))

    result = await postgres_repository.delete_game_history("g1")
    assert result.deleted_events == 3
    assert result.deleted_snapshots == 1
    assert await postgres_repository.list_events("g1") == []
    assert await postgres_repository.list_snapshots("g1") == []
    # The untouched game survives.
    assert {s.game_id for s in await postgres_repository.list_games()} == {"g2"}

    # Idempotent: deleting again removes nothing.
    again = await postgres_repository.delete_game_history("g1")
    assert again.deleted_events == 0
    assert again.deleted_snapshots == 0


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_timeline_summary_prunes_jsonb_on_postgres(postgres_repository):
    """The Postgres pruning path is dialect-specific, so it needs a real Postgres.

    Unit tests exercise the sqlite ``json_remove`` branch; this covers the
    ``jsonb - 'key'`` branch and the ``#>>`` text reads of the round and step,
    including that a dotted step id survives as a string and round 0 as 0.
    """
    payload = {
        "state": {
            "deltas": [{"i": i} for i in range(20)],
            "game": {
                "roundNumber": 0,
                "stepId": "0.1",
                "mode": "in progress",
                "cardById": {f"card-{i}": {"text": "x" * 200} for i in range(50)},
            },
        },
        "status": "in progress",
        "action_args": {"type": "next_step"},
    }
    envelope = EventEnvelope(
        game_id="g1",
        actor="game-service",
        event_type="game_state",
        payload=payload,
        occurred_at=datetime.now(timezone.utc),
        idempotency_key="g1:game-service:0",
        producer_offset=0,
    )
    await postgres_repository.commit_event(envelope)
    await postgres_repository.commit_event(
        EventEnvelope(
            game_id="g1",
            actor="agent",
            event_type="agent_decision",
            payload={
                "intended_action": "move_card",
                "conversation_context": [{"role": "user", "content": "x" * 5000}],
            },
            occurred_at=datetime.now(timezone.utc),
            idempotency_key="g1:agent:0",
            producer_offset=1,
        )
    )

    state_entry, agent_entry = await postgres_repository.list_event_summaries("g1")

    assert state_entry.payload["state"] == {"game": {"roundNumber": 0, "stepId": "0.1"}}
    assert state_entry.payload["status"] == "in progress"
    assert state_entry.payload["action_args"] == {"type": "next_step"}
    assert "conversation_context" not in agent_entry.payload
    assert agent_entry.payload["intended_action"] == "move_card"
    assert "state" not in agent_entry.payload

    # The full payload is still intact on the events read.
    full_state, _ = await postgres_repository.list_events("g1")
    assert len(full_state.payload["state"]["game"]["cardById"]) == 50


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_timeline_summary_paging_on_postgres(postgres_repository):
    for offset in range(5):
        await postgres_repository.commit_event(_envelope("g1", offset=offset))
    page1 = await postgres_repository.list_event_summaries("g1", after_seq=0, limit=2)
    assert [e.seq for e in page1] == [1, 2]
    page2 = await postgres_repository.list_event_summaries("g1", after_seq=2, limit=2)
    assert [e.seq for e in page2] == [3, 4]
    assert page2[0].payload == {"offset": 2}
