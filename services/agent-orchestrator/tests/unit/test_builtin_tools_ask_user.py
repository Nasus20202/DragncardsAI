from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_orchestrator.runtime.builtin_tools import (
    _close_or_take_late_answer,
    build_builtin_registry,
    make_ask_user_handler,
    validate_ask_user_arguments,
)
from agent_orchestrator.runtime.live_events import InMemoryLiveEventBus
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.db import create_engine, create_session_factory
from agent_orchestrator.storage.migrations import ensure_schema
from agent_orchestrator.storage.repository import Repository

from .builtin_tools_test_support import (
    await_job_event,
    live_event_bus,
    make_job,
    skill_registry,
)

CHOICES = [
    {"label": "Spider-Man", "value": "spider-man"},
    {"label": "She-Hulk", "value": "she-hulk", "description": "Hits hard."},
]


@pytest.fixture
async def repository(tmp_path: Path):
    """A file-backed SQLite repository, not the shared in-memory one.

    These tests write an answer or a cancellation from the test coroutine while
    the tool's wait loop polls from another. SQLAlchemy backs a
    ``sqlite+aiosqlite:///:memory:`` engine with a StaticPool — one DBAPI
    connection shared by every session — so the poll loop's session closing
    issues a ROLLBACK on the very connection the writer is mid-transaction on,
    and the write silently vanishes. A file-backed database gives each session
    its own connection, as Postgres does in production, so the concurrency these
    tests exercise is the real thing rather than an artifact of the fixture.
    """
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'questions.db'}")
    await ensure_schema(engine)
    try:
        yield Repository(create_session_factory(engine))
    finally:
        await engine.dispose()


async def _make_job_row(repository: Repository):
    session = await repository.create_session("player", {})
    job = await repository.enqueue_prompt_job(
        session.id, prompt="go", metadata_json={}, max_attempts=1
    )
    assert job is not None
    return session, job


def _handler(repository, live_event_bus, session_id, job_id, **kwargs):
    return make_ask_user_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session_id,
        job_id=job_id,
        job=make_job(parent_job_id=None, job_type="prompt"),
        poll_interval_seconds=0.02,
        **kwargs,
    )


# --- argument validation ------------------------------------------------------


def test_validate_accepts_a_well_formed_question():
    validated = validate_ask_user_arguments(
        {"question": "  Who plays?  ", "choices": CHOICES, "allow_free_text": True}
    )
    assert validated.error is None
    assert validated.question == "Who plays?"
    assert validated.allow_free_text is True
    assert [choice["value"] for choice in validated.choices] == [
        "spider-man",
        "she-hulk",
    ]
    assert validated.choices[1]["description"] == "Hits hard."


@pytest.mark.parametrize(
    "arguments",
    [
        {"choices": CHOICES},
        {"question": "   ", "choices": CHOICES},
        {"question": "x" * 2001, "choices": CHOICES},
        {"question": "Who?", "choices": []},
        {"question": "Who?", "choices": "spider-man"},
        {"question": "Who?", "choices": [{"label": "A"}]},
        {"question": "Who?", "choices": [{"label": "", "value": "a"}]},
        {"question": "Who?", "choices": [{"label": "A", "value": "a"}] * 9},
        {"question": "Who?", "choices": ["spider-man"]},
        {"question": "Who?", "choices": [{"label": "A", "value": "x" * 201}]},
        {
            "question": "Who?",
            "choices": [{"label": "A", "value": "a", "description": 7}],
        },
        {"question": "Who?", "choices": CHOICES, "allow_free_text": "yes"},
    ],
)
def test_validate_rejects_malformed_arguments(arguments):
    assert validate_ask_user_arguments(arguments).error is not None


def test_validate_rejects_duplicate_choice_values():
    # Two choices sharing a value would make an answer ambiguous, because the
    # answer endpoint matches an answer to a choice by value.
    validated = validate_ask_user_arguments(
        {
            "question": "Who?",
            "choices": [
                {"label": "Spidey", "value": "spider-man"},
                {"label": "Spider-Man", "value": "spider-man"},
            ],
        }
    )
    assert validated.error is not None
    assert "duplicates" in validated.error


# --- registry and gating ------------------------------------------------------


async def test_ask_user_is_offered_to_a_master_job(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
):
    registry = build_builtin_registry(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id="s",
        job_id="j",
        skill_assignments=[],
        job=make_job(parent_job_id=None, job_type="prompt"),
    )
    names = [tool["function"]["name"] for tool in registry.as_openai_tools()]
    assert "ask_user" in names

    definition = registry.get("ask_user")
    assert definition is not None
    assert definition.parameters["required"] == ["question", "choices"]
    assert definition.parameters["properties"]["choices"]["maxItems"] == 8


@pytest.mark.parametrize(
    "job_kwargs",
    [{"parent_job_id": "parent"}, {"job_type": "compaction"}],
)
async def test_ask_user_is_not_offered_to_a_non_master_job(
    repository: Repository,
    live_event_bus: InMemoryLiveEventBus,
    skill_registry: SkillRegistry,
    job_kwargs,
):
    registry = build_builtin_registry(
        skill_registry=skill_registry,
        repository=repository,
        live_event_bus=live_event_bus,
        session_id="s",
        job_id="j",
        skill_assignments=[],
        job=make_job(**job_kwargs),
    )
    assert registry.get("ask_user") is None


async def test_a_child_job_calling_ask_user_is_refused(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = make_ask_user_handler(
        repository=repository,
        live_event_bus=live_event_bus,
        session_id=session.id,
        job_id=job.id,
        job=make_job(parent_job_id="parent"),
        poll_interval_seconds=0.02,
    )

    result = await handler({"question": "Who?", "choices": CHOICES})

    assert result["is_error"] is True
    assert "top-level" in result["content"][0]["text"]


async def test_a_rejected_question_records_nothing(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = _handler(repository, live_event_bus, session.id, job.id)

    result = await handler({"question": "Who?", "choices": []})

    assert result["is_error"] is True
    events = await repository.list_events(job.id)
    assert [e.event_type for e in events if "question" in e.event_type] == []


# --- the answered path --------------------------------------------------------


async def test_the_answer_comes_back_to_the_model_as_the_tool_result(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = _handler(repository, live_event_bus, session.id, job.id)

    waiting = asyncio.create_task(
        handler({"question": "Who plays?", "choices": CHOICES})
    )
    asked = await await_job_event(repository, job.id, "user_question")
    question_id = asked.payload_json["question_id"]
    assert asked.payload_json["choices"] == CHOICES
    assert asked.payload_json["allow_free_text"] is False

    answered = await repository.answer_job_question(
        question_id, source="choice", value="she-hulk", label="She-Hulk", text=None
    )
    assert answered is not None

    result = await asyncio.wait_for(waiting, timeout=10)

    assert result["is_error"] is False
    assert "She-Hulk" in result["content"][0]["text"]
    assert "she-hulk" in result["content"][0]["text"]


async def test_a_free_text_answer_is_reported_verbatim(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = _handler(repository, live_event_bus, session.id, job.id)

    waiting = asyncio.create_task(
        handler({"question": "Who?", "choices": CHOICES, "allow_free_text": True})
    )
    asked = await await_job_event(repository, job.id, "user_question")
    await repository.answer_job_question(
        asked.payload_json["question_id"],
        source="free_text",
        value=None,
        label=None,
        text="Ms Marvel, actually",
    )

    result = await asyncio.wait_for(waiting, timeout=10)

    assert result["is_error"] is False
    assert "Ms Marvel, actually" in result["content"][0]["text"]


# --- nobody answers -----------------------------------------------------------


async def test_an_unanswered_question_times_out_and_is_closed(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = _handler(
        repository, live_event_bus, session.id, job.id, timeout_seconds=0.05
    )

    result = await handler({"question": "Who?", "choices": CHOICES})

    # Not an error: marking a timeout an error invites the model to retry the
    # tool straight away, which asks the same unanswered question again.
    assert result["is_error"] is False
    text = result["content"][0]["text"]
    assert "Nobody answered" in text
    assert "again" in text

    events = await repository.list_events(job.id)
    closed = [e for e in events if e.event_type == "user_question_closed"]
    assert len(closed) == 1
    assert closed[0].payload_json["reason"] == "timeout"

    stored = await repository.get_job_question(closed[0].payload_json["question_id"])
    assert stored is not None
    assert stored.status == "closed"
    assert stored.closed_reason == "timeout"


async def test_a_late_answer_to_a_timed_out_question_is_refused(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = _handler(
        repository, live_event_bus, session.id, job.id, timeout_seconds=0.05
    )

    await handler({"question": "Who?", "choices": CHOICES})
    closed = await await_job_event(repository, job.id, "user_question_closed")

    late = await repository.answer_job_question(
        closed.payload_json["question_id"],
        source="choice",
        value="she-hulk",
        label="She-Hulk",
        text=None,
    )
    assert late is None


async def test_cancelling_the_job_closes_the_question(
    repository: Repository, live_event_bus: InMemoryLiveEventBus
):
    session, job = await _make_job_row(repository)
    handler = _handler(repository, live_event_bus, session.id, job.id)

    waiting = asyncio.create_task(handler({"question": "Who?", "choices": CHOICES}))
    asked = await await_job_event(repository, job.id, "user_question")
    cancelled = await repository.request_cancel(job.id)
    assert cancelled is not None
    assert cancelled.cancellation_requested_at is not None

    result = await asyncio.wait_for(waiting, timeout=10)

    assert result["is_error"] is True
    assert "cancelled" in result["content"][0]["text"]

    stored = await repository.get_job_question(asked.payload_json["question_id"])
    assert stored is not None
    assert stored.status == "closed"
    assert stored.closed_reason == "cancelled"


async def test_an_answer_racing_the_timeout_still_wins(repository: Repository):
    """Closing is conditional, so losing that race must return the answer.

    The user clicked in the same instant the wait gave up. Their answer is
    recorded, so it is the outcome the model should see.
    """
    session, job = await _make_job_row(repository)
    question = await repository.create_job_question(
        job.id, session.id, question="Who?", choices=CHOICES, allow_free_text=False
    )
    await repository.answer_job_question(
        question.id, source="choice", value="she-hulk", label="She-Hulk", text=None
    )

    outcome = await _close_or_take_late_answer(
        repository=repository, question_id=question.id, reason="timeout"
    )

    assert outcome.kind == "answered"
    assert outcome.question is not None
    assert outcome.question.answer_value == "she-hulk"


# --- the store's conditional transitions --------------------------------------


async def test_only_one_of_two_racing_answers_is_recorded(repository: Repository):
    session, job = await _make_job_row(repository)
    question = await repository.create_job_question(
        job.id, session.id, question="Who?", choices=CHOICES, allow_free_text=False
    )

    first = await repository.answer_job_question(
        question.id, source="choice", value="she-hulk", label="She-Hulk", text=None
    )
    second = await repository.answer_job_question(
        question.id,
        source="choice",
        value="spider-man",
        label="Spider-Man",
        text=None,
    )

    # Only the first caller wins the conditional update. The second is told so
    # by a None return rather than overwriting the recorded answer.
    assert first is not None
    assert second is None

    stored = await repository.get_job_question(question.id)
    assert stored is not None
    assert stored.status == "answered"
    assert stored.answer_value == "she-hulk"


async def test_a_closed_question_cannot_then_be_answered(repository: Repository):
    session, job = await _make_job_row(repository)
    question = await repository.create_job_question(
        job.id, session.id, question="Who?", choices=CHOICES, allow_free_text=False
    )

    assert (
        await repository.close_job_question(question.id, reason="timeout") is not None
    )
    assert await repository.close_job_question(question.id, reason="timeout") is None
    assert (
        await repository.answer_job_question(
            question.id, source="choice", value="she-hulk", label="She-Hulk", text=None
        )
        is None
    )


async def test_deleting_the_session_removes_its_questions(repository: Repository):
    session, job = await _make_job_row(repository)
    question = await repository.create_job_question(
        job.id, session.id, question="Who?", choices=CHOICES, allow_free_text=False
    )

    assert await repository.delete_session(session.id) is True
    assert await repository.get_job_question(question.id) is None
