"""The answer endpoint's server-side validation.

The browser is never trusted here. Every test in this file exists because a
client could send something the model never offered, or answer a question that
is no longer waiting, and the endpoint has to refuse rather than let a submitted
answer widen what the model asked for.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

CHOICES = [
    {"label": "Spider-Man", "value": "spider-man"},
    {"label": "She-Hulk", "value": "she-hulk", "description": "Hits hard."},
]


def _create_session(client: TestClient) -> str:
    return client.post("/sessions", json={"name": "player"}).json()["session"]["id"]


async def _pending_question(app, client: TestClient, *, allow_free_text=False):
    """Create a running job with one pending question on it."""
    session_id = _create_session(client)
    job = client.post(f"/sessions/{session_id}/prompts", json={"prompt": "go"}).json()[
        "job"
    ]
    repo = app.state.repository
    question = await repo.create_job_question(
        job["id"],
        session_id,
        question="Who plays?",
        choices=CHOICES,
        allow_free_text=allow_free_text,
    )
    return job["id"], question.id


def _answer(client: TestClient, job_id: str, question_id: str, body: dict):
    return client.post(f"/jobs/{job_id}/questions/{question_id}/answer", json=body)


async def test_answering_with_an_offered_choice_records_it(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)

        response = _answer(client, job_id, question_id, {"choice_value": "she-hulk"})

        assert response.status_code == 200
        question = response.json()["question"]
        assert question["status"] == "answered"
        assert question["answer_source"] == "choice"
        assert question["answer_value"] == "she-hulk"
        # The label is read back from the stored question, not taken from the
        # request, so a client cannot relabel the choice it picked.
        assert question["answer_label"] == "She-Hulk"
        assert [choice["value"] for choice in question["choices"]] == [
            "spider-man",
            "she-hulk",
        ]

        events = client.get(f"/jobs/{job_id}/events").json()["events"]
        answered = [e for e in events if e["event_type"] == "user_question_answered"]
        assert len(answered) == 1
        assert answered[0]["payload"]["question_id"] == question_id
        assert answered[0]["payload"]["value"] == "she-hulk"


async def test_a_value_that_was_never_offered_is_refused(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)

        response = _answer(client, job_id, question_id, {"choice_value": "thor"})

        assert response.status_code == 400
        assert "not offered" in response.json()["detail"]
        # The question is untouched, so the run keeps waiting for a real answer.
        stored = await app.state.repository.get_job_question(question_id)
        assert stored.status == "pending"


async def test_free_text_is_refused_when_the_question_did_not_permit_it(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)

        response = _answer(client, job_id, question_id, {"text": "Ms Marvel"})

        assert response.status_code == 400
        assert "free-text" in response.json()["detail"]
        stored = await app.state.repository.get_job_question(question_id)
        assert stored.status == "pending"


async def test_free_text_is_accepted_when_the_question_permitted_it(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client, allow_free_text=True)

        response = _answer(client, job_id, question_id, {"text": "  Ms Marvel  "})

        assert response.status_code == 200
        question = response.json()["question"]
        assert question["status"] == "answered"
        assert question["answer_source"] == "free_text"
        assert question["answer_text"] == "Ms Marvel"


async def test_empty_free_text_is_refused(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client, allow_free_text=True)

        response = _answer(client, job_id, question_id, {"text": "   "})

        assert response.status_code == 400


async def test_both_answer_forms_at_once_are_refused(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client, allow_free_text=True)

        response = _answer(
            client,
            job_id,
            question_id,
            {"choice_value": "she-hulk", "text": "Ms Marvel"},
        )

        assert response.status_code == 400
        assert "exactly one" in response.json()["detail"]


async def test_neither_answer_form_is_refused(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)

        response = _answer(client, job_id, question_id, {})

        assert response.status_code == 400


async def test_the_second_answer_is_refused_and_changes_nothing(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)

        first = _answer(client, job_id, question_id, {"choice_value": "she-hulk"})
        assert first.status_code == 200

        second = _answer(client, job_id, question_id, {"choice_value": "spider-man"})

        assert second.status_code == 409
        assert "already been answered" in second.json()["detail"]

        stored = await app.state.repository.get_job_question(question_id)
        assert stored.answer_value == "she-hulk"

        # And exactly one answered event reached the timeline, so the model can
        # never observe two answers to one question.
        events = client.get(f"/jobs/{job_id}/events").json()["events"]
        answered = [e for e in events if e["event_type"] == "user_question_answered"]
        assert len(answered) == 1


async def test_a_closed_question_is_not_answerable(app):
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)
        await app.state.repository.close_job_question(question_id, reason="timeout")

        response = _answer(client, job_id, question_id, {"choice_value": "she-hulk"})

        assert response.status_code == 409
        assert "no longer awaiting" in response.json()["detail"]


async def test_a_question_of_a_finished_job_is_not_answerable(app):
    """The case where the run that was waiting is gone.

    Nothing closed the question because nothing was alive to close it, so the
    row is still pending. Accepting an answer nobody will read would be a lie.
    """
    with TestClient(app) as client:
        job_id, question_id = await _pending_question(app, client)
        await app.state.repository.mark_job_completed(job_id, "done")

        response = _answer(client, job_id, question_id, {"choice_value": "she-hulk"})

        assert response.status_code == 409
        assert "already finished" in response.json()["detail"]


async def test_an_unknown_question_is_not_found(app):
    with TestClient(app) as client:
        job_id, _ = await _pending_question(app, client)

        response = _answer(
            client,
            job_id,
            "00000000-0000-0000-0000-000000000000",
            {"choice_value": "a"},
        )

        assert response.status_code == 404


async def test_an_unknown_job_is_not_found(app):
    with TestClient(app) as client:
        _, question_id = await _pending_question(app, client)

        response = _answer(
            client, "00000000-0000-0000-0000-000000000000", question_id, {}
        )

        assert response.status_code == 404


async def test_a_question_cannot_be_answered_through_another_job(app):
    """Scoping the lookup to the path's job is what enforces this."""
    with TestClient(app) as client:
        _, question_id = await _pending_question(app, client)
        other_job_id, _ = await _pending_question(app, client)

        response = _answer(
            client, other_job_id, question_id, {"choice_value": "she-hulk"}
        )

        assert response.status_code == 404


async def test_a_forged_value_is_refused_however_the_ui_was_rendered(app):
    """The question surface is rendered from a model-authored DSL (OpenUI Lang).

    That is a larger rendering surface than a list of buttons, so this asserts
    the property the surface is not allowed to weaken: the endpoint validates
    ``choice_value`` against ``choices_json`` read back from the row, so nothing
    a rendered program can express becomes an acceptable answer. Each value
    below is one a forged or model-authored control could plausibly submit.
    """
    forgeries = [
        # A label instead of the value it belongs to.
        "She-Hulk",
        # The description.
        "Hits hard.",
        # A hero that was never offered.
        "thor",
        # Case and whitespace variants of a real value: matching is exact.
        "SHE-HULK",
        " she-hulk",
        "she-hulk ",
        # Structural guesses at how the stored row is shaped.
        "0",
        "1",
        "*",
        "",
    ]
    with TestClient(app) as client:
        for forged in forgeries:
            job_id, question_id = await _pending_question(app, client)

            response = _answer(client, job_id, question_id, {"choice_value": forged})

            assert response.status_code == 400, forged
            assert "not offered" in response.json()["detail"], forged
            # Refused, not recorded: the run is still waiting for a real answer.
            stored = await app.state.repository.get_job_question(question_id)
            assert stored.status == "pending", forged
            assert stored.answer_value is None, forged
            assert stored.answer_label is None, forged
