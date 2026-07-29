from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_orchestrator.integrations.bifrost import ChatResponse
from agent_orchestrator.runtime.compaction import (
    NothingToCompactError,
    perform_compaction,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.tokens import estimate_tokens_for_messages
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository


@pytest.fixture
async def repository(tmp_path: Path):
    database_path = tmp_path / "compaction_service.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    await ensure_schema(engine)
    repo = Repository(create_session_factory(engine))
    try:
        yield repo
    finally:
        await engine.dispose()


async def make_session_with_model(repo: Repository):
    session = await repo.create_session("test", {})
    model_config = await repo.set_model_config(
        session.id,
        provider_id="openai",
        model_name="gpt-4o-mini",
        gateway_options={},
        provider_options={},
    )
    assert model_config is not None
    return session, model_config


async def make_completed_job(
    repo: Repository,
    session_id: str,
    prompt: str,
    output: str,
    *,
    tool_name: str | None = None,
    tool_arguments: dict | None = None,
    tool_result: dict | None = None,
) -> str:
    job = await repo.enqueue_prompt_job(
        session_id, prompt=prompt, metadata_json={}, max_attempts=1
    )
    assert job is not None
    await repo.claim_next_job()
    await repo.append_event(job.id, session_id, "model_output", {"text": output})
    if tool_name is not None:
        await repo.append_event(
            job.id,
            session_id,
            "tool_call",
            {
                "tool_call_id": f"call-{tool_name}",
                "exposed_tool_name": tool_name,
                "arguments": tool_arguments or {},
            },
        )
        await repo.append_event(
            job.id,
            session_id,
            "tool_result",
            {
                "tool_call_id": f"call-{tool_name}",
                "exposed_tool_name": tool_name,
                "result": tool_result or {},
            },
        )
    await repo.mark_job_completed(job.id, output)
    return job.id


class CapturingBifrost:
    """Records the summarization request instead of sending it."""

    def __init__(self, summary: str = "Updated summary"):
        self.summary = summary
        self.requests: list[list[dict]] = []

    async def chat_completion(self, *args, **kwargs):
        self.requests.append(args[2])
        return ChatResponse(
            content=self.summary,
            tool_calls=[],
            raw={"usage": {"total_tokens": 21}},
        )

    @property
    def last_history(self) -> str:
        """The user message the summarizer was handed."""
        return self.requests[-1][-1]["content"]


@pytest.mark.asyncio
async def test_perform_compaction_uses_token_count_fallback_when_response_has_no_usage(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    await make_completed_job(repository, session.id, "turn 1", "response 1")

    bifrost = AsyncMock()
    bifrost.chat_completion.return_value = ChatResponse(
        content="Summary only",
        tool_calls=[],
        raw={},
    )

    record = await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )

    assert record.summary_text == "Summary only"
    assert record.tokens_used > 0


@pytest.mark.asyncio
async def test_perform_compaction_includes_previous_summary_and_publishes_event(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    first_job_id = await make_completed_job(
        repository, session.id, "turn 1", "response 1"
    )
    await repository.create_compaction_record(
        session.id,
        summary_text="Earlier summary",
        covers_up_to_job_id=first_job_id,
        tokens_used=12,
    )
    await make_completed_job(repository, session.id, "turn 2", "response 2")
    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next", metadata_json={}, max_attempts=1
    )
    assert current_job is not None

    captured_messages = []

    async def fake_chat_completion(*args, **kwargs):
        captured_messages.extend(args[3])
        return ChatResponse(
            content="Updated summary",
            tool_calls=[],
            raw={"usage": {"total_tokens": 21}},
        )

    live_event_bus = InMemoryLiveEventBus()
    subscriber = await live_event_bus.subscribe(current_job.id)
    try:
        record = await perform_compaction(
            repository=repository,
            bifrost_client=type(
                "FakeBifrost", (), {"chat_completion": fake_chat_completion}
            )(),
            session_id=session.id,
            model_config=model_config,
            current_job_id=current_job.id,
            live_event_bus=live_event_bus,
        )
        event = await subscriber.get(0.1)
    finally:
        await subscriber.aclose()

    assert record.summary_text == "Updated summary"
    assert any(
        message["role"] == "system"
        and "Previous summary:\nEarlier summary" in message["content"]
        for message in captured_messages
    )
    assert event is not None
    assert event.event_type == "compaction"
    assert event.payload_json["summary_text"] == "Updated summary"
    assert event.payload_json["tokens_used"] == 21
    assert event.payload_json["truncated_events"] == 0
    assert event.payload_json["dropped_history_entries"] == 0


@pytest.mark.asyncio
async def test_perform_compaction_rejects_completed_jobs_without_history_content(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    job = await repository.enqueue_prompt_job(
        session.id, prompt="", metadata_json={}, max_attempts=1
    )
    assert job is not None
    await repository.claim_next_job()
    await repository.mark_job_completed(job.id, "")

    bifrost = AsyncMock()

    with pytest.raises(ValueError, match="No history content to compact"):
        await perform_compaction(
            repository=repository,
            bifrost_client=bifrost,
            session_id=session.id,
            model_config=model_config,
        )

    bifrost.chat_completion.assert_not_called()


# ---------------------------------------------------------------------------
# The compaction input is checkpointed (A1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_compaction_does_not_re_read_the_first_ones_jobs(
    repository: Repository,
):
    """Two successive compactions, measured. The second reads only its own span.

    This is the growth the checkpoint removes: before it, every compaction
    re-read the whole session, so the second cost at least as much as the first.
    """
    session, model_config = await make_session_with_model(repository)
    for turn in range(1, 4):
        await make_completed_job(
            repository, session.id, f"pre-checkpoint turn {turn}", f"answer {turn}"
        )

    bifrost = CapturingBifrost(summary="Summary of the first span")
    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )
    first_input = bifrost.last_history
    assert "pre-checkpoint turn 1" in first_input

    for turn in range(4, 6):
        await make_completed_job(
            repository, session.id, f"post-checkpoint turn {turn}", f"answer {turn}"
        )

    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )
    second_input = bifrost.last_history

    # The span since the checkpoint, and nothing before it.
    assert "post-checkpoint turn 4" in second_input
    assert "post-checkpoint turn 5" in second_input
    for turn in range(1, 4):
        assert f"pre-checkpoint turn {turn}" not in second_input

    # The previous summary is what stands in for the span that is no longer read
    # raw, and it is supplied as prior context rather than as history.
    assert any(
        message["role"] == "system"
        and "Previous summary:\nSummary of the first span" in message["content"]
        for message in bifrost.requests[-1]
    )

    # Measured, not reasoned: two more turns of history, a smaller input.
    assert len(second_input) < len(first_input)


@pytest.mark.asyncio
async def test_from_session_start_ignores_the_checkpoint(repository: Repository):
    """The recovery path re-reads everything, so a lossy summary can be rebuilt."""
    session, model_config = await make_session_with_model(repository)
    for turn in range(1, 4):
        await make_completed_job(
            repository, session.id, f"pre-checkpoint turn {turn}", f"answer {turn}"
        )

    bifrost = CapturingBifrost(summary="Summary of the first span")
    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )
    await make_completed_job(
        repository, session.id, "post-checkpoint turn 4", "answer 4"
    )

    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
        from_session_start=True,
    )
    rebuilt_input = bifrost.last_history

    for turn in range(1, 4):
        assert f"pre-checkpoint turn {turn}" in rebuilt_input
    assert "post-checkpoint turn 4" in rebuilt_input


@pytest.mark.asyncio
async def test_nothing_new_since_the_checkpoint_is_nothing_to_compact(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    await make_completed_job(repository, session.id, "turn 1", "answer 1")

    bifrost = CapturingBifrost()
    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )

    with pytest.raises(NothingToCompactError):
        await perform_compaction(
            repository=repository,
            bifrost_client=bifrost,
            session_id=session.id,
            model_config=model_config,
        )
    assert len(bifrost.requests) == 1


# ---------------------------------------------------------------------------
# The compaction input is bounded per event (A2) and in total (A3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_oversized_tool_result_is_truncated_with_a_marker(
    repository: Repository,
):
    session, model_config = await make_session_with_model(repository)
    await make_completed_job(
        repository,
        session.id,
        "search for cards",
        "here they are",
        tool_name="game-service_search_cards_marvel_champions",
        tool_result={"cards": "x" * 5_000},
    )

    bifrost = CapturingBifrost()
    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
        event_char_budget=500,
    )
    history = bifrost.last_history

    assert "… [truncated, " in history
    assert "chars omitted]" in history
    assert "x" * 501 not in history


@pytest.mark.asyncio
async def test_a_board_sized_tool_result_is_not_truncated(repository: Repository):
    """A full simplified board must survive the default budget intact.

    Measured against the real deployment: `get_game_state` results run to about
    6.3k characters at the 99th percentile, against a 20k default.
    """
    session, model_config = await make_session_with_model(repository)
    board = {"zones": {f"card-{index}": "a" * 100 for index in range(63)}}
    await make_completed_job(
        repository,
        session.id,
        "what is on the board",
        "reading the board",
        tool_name="game-service_get_game_state",
        tool_result=board,
    )
    assert 6_300 < len(str(board)) < 20_000

    bifrost = CapturingBifrost()
    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
    )

    assert "truncated" not in bifrost.last_history
    assert str(board) in bifrost.last_history


@pytest.mark.asyncio
async def test_the_assembled_request_is_kept_under_the_ceiling(repository: Repository):
    """Oldest-first drops, counted, until the estimate fits."""
    session, model_config = await make_session_with_model(repository)
    for turn in range(1, 9):
        await make_completed_job(
            repository,
            session.id,
            f"turn {turn}",
            f"answer {turn} " + "filler words to spend tokens on " * 40,
        )

    ceiling = 2_000
    bifrost = CapturingBifrost()
    live_event_bus = InMemoryLiveEventBus()
    current_job = await repository.enqueue_prompt_job(
        session.id, prompt="next", metadata_json={}, max_attempts=1
    )
    assert current_job is not None
    subscriber = await live_event_bus.subscribe(current_job.id)
    try:
        await perform_compaction(
            repository=repository,
            bifrost_client=bifrost,
            session_id=session.id,
            model_config=model_config,
            current_job_id=current_job.id,
            live_event_bus=live_event_bus,
            max_input_tokens=ceiling,
        )
        event = await subscriber.get(0.1)
    finally:
        await subscriber.aclose()

    assert estimate_tokens_for_messages(bifrost.requests[-1]) <= ceiling
    history = bifrost.last_history
    # Oldest dropped, newest kept.
    assert "turn 8" in history
    assert "turn 1" not in history

    assert event is not None
    assert event.payload_json["dropped_history_entries"] > 0


@pytest.mark.asyncio
async def test_no_ceiling_means_no_drops(repository: Repository):
    session, model_config = await make_session_with_model(repository)
    for turn in range(1, 4):
        await make_completed_job(
            repository, session.id, f"turn {turn}", f"answer {turn}"
        )

    bifrost = CapturingBifrost()
    await perform_compaction(
        repository=repository,
        bifrost_client=bifrost,
        session_id=session.id,
        model_config=model_config,
        max_input_tokens=None,
    )

    history = bifrost.last_history
    for turn in range(1, 4):
        assert f"turn {turn}" in history
