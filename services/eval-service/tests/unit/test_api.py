from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from eval_service.config import Settings
from eval_service.runtime.app import create_app
from eval_service.schema_migrations import ensure_schema
from eval_service.storage.db import create_session_factory
from eval_service.storage.repository import Repository
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    agent_event,
    state_event,
)


@pytest_asyncio.fixture
async def repo_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    yield Repository(create_session_factory(engine))
    await engine.dispose()


def _game(game_id="g1"):
    return [
        state_event(game_id=game_id, seq=1, round_number=1),
        agent_event(game_id=game_id, seq=2),
        state_event(game_id=game_id, seq=3, round_number=1, status="win"),
    ]


def _client(repo, history, judge, settings):
    app = create_app(
        settings=settings,
        repository=repo,
        history_client=history,
        judge_client=judge,
        start_worker=False,
    )
    return TestClient(app)


def test_health_ok(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_ready_reports_checks_and_no_secrets(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.get("/ready")
        body = resp.json()
        assert resp.status_code == 200
        assert body["status"] == "ok"
        assert body["checks"] == {
            "database": True,
            "history": True,
            "bifrost": True,
        }
        assert body["judge_configured"] is True
        # No secret echoed anywhere in the response.
        assert "key" not in resp.text.lower()


def test_ready_degraded_when_no_judge_model(repo_factory):
    settings = Settings(eval_judge_model="")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        body = client.get("/ready").json()
        assert body["status"] == "degraded"
        assert body["judge_configured"] is False


def test_create_request_returns_targets(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["created_count"] == 1
        assert body["targets"][0]["target_seq"] == 2
        assert body["targets"][0]["status"] == "pending"
        request_id = body["request_id"]

        status = client.get(f"/games/g1/evaluations/{request_id}").json()
        assert status["request_id"] == request_id
        assert status["status"] == "pending"


def test_create_request_empty_selection_422(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {}},
        )
        # Pydantic validation rejects an empty selection.
        assert resp.status_code == 422


def test_create_request_unknown_game_404(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post(
            "/games/none/evaluations",
            json={"scope": "move", "selection": {"whole_game": True}},
        )
        assert resp.status_code == 404


def test_invalid_game_id_rejected_at_boundary(repo_factory):
    # A game_id outside the strict charset is rejected (404) before any history
    # read or downstream URL is built.
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post(
            "/games/bad%20id/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        )
        assert resp.status_code == 404
        # A 65+ char id is also rejected.
        long_id = "a" * 65
        resp2 = client.get(f"/games/{long_id}/evaluations/whatever")
        assert resp2.status_code == 404


def test_create_request_with_judge_config_accepted(repo_factory, tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "SKILL.md").write_text("body", encoding="utf-8")
    settings = Settings(
        eval_judge_model="anthropic/claude-x", skill_roots=str(tmp_path)
    )
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post(
            "/games/g1/evaluations",
            json={
                "scope": "move",
                "selection": {"seqs": [2]},
                "judge": {
                    "model_name": "openrouter/x/y",
                    "reasoning": {"enabled": True, "effort": "high"},
                    "skills": ["rules"],
                },
            },
        )
        assert resp.status_code == 201
        assert resp.json()["created_count"] == 1


def test_create_request_unknown_skill_400(repo_factory, tmp_path):
    settings = Settings(
        eval_judge_model="anthropic/claude-x", skill_roots=str(tmp_path)
    )
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post(
            "/games/g1/evaluations",
            json={
                "scope": "move",
                "selection": {"seqs": [2]},
                "judge": {"skills": ["does-not-exist"]},
            },
        )
        assert resp.status_code == 400
        assert "does-not-exist" in resp.json()["detail"]


def test_cancel_unknown_request_404(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        resp = client.post("/games/g1/evaluations/nope/cancel")
        assert resp.status_code == 404


def test_cancel_pending_targets(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        created = client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        ).json()
        request_id = created["request_id"]
        # Targets are still pending (no worker running) -> cancel them.
        resp = client.post(f"/games/g1/evaluations/{request_id}/cancel")
        assert resp.status_code == 200
        assert resp.json() == {"request_id": request_id, "cancelled": 1}

        status = client.get(f"/games/g1/evaluations/{request_id}").json()
        assert status["status"] == "cancelled"
        assert status["targets"][0]["status"] == "cancelled"
        assert status["targets"][0]["verdict"] is None

        # Cancelling again is a no-op.
        resp2 = client.post(f"/games/g1/evaluations/{request_id}/cancel")
        assert resp2.json()["cancelled"] == 0


def test_delete_terminal_request_removes_it(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        request_id = client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        ).json()["request_id"]
        # Cancel so the request becomes fully terminal, then clear it.
        client.post(f"/games/g1/evaluations/{request_id}/cancel")

        resp = client.delete(f"/evaluations/{request_id}")
        assert resp.status_code == 204

        # Gone from the cross-game listing and the per-request lookup.
        assert client.get("/evaluations").json() == {"requests": []}
        assert client.get(f"/games/g1/evaluations/{request_id}").status_code == 404


def test_delete_running_request_409_and_remains(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    # No worker -> the target stays pending (non-terminal): it cannot be cleared.
    with _client(repo_factory, history, judge, settings) as client:
        request_id = client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        ).json()["request_id"]

        resp = client.delete(f"/evaluations/{request_id}")
        assert resp.status_code == 409
        # Still present after the rejected clear.
        body = client.get("/evaluations").json()
        assert [r["request_id"] for r in body["requests"]] == [request_id]


def test_delete_missing_request_404(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game()})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        assert client.delete("/evaluations/does-not-exist").status_code == 404


@pytest.mark.asyncio
async def test_clear_evaluations_removes_only_terminal(repo_and_factory):
    repo, factory = repo_and_factory
    await _seed_request(
        factory,
        request_id="done",
        game_id="g1",
        created_at=_at(1),
        target_statuses=["completed", "failed"],
    )
    await _seed_request(
        factory,
        request_id="live",
        game_id="g2",
        created_at=_at(2),
        target_statuses=["completed", "running"],
    )

    deleted = await repo.delete_terminal_requests()
    assert deleted == 1
    remaining = await repo.list_requests(limit=50, active_only=False)
    assert [r.request_id for r, _ in remaining] == ["live"]


def test_clear_evaluations_endpoint(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game("g1"), "g2": _game("g2")})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        # One request that we cancel (terminal), one left pending (active).
        terminal_id = client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        ).json()["request_id"]
        client.post(f"/games/g1/evaluations/{terminal_id}/cancel")
        active_id = client.post(
            "/games/g2/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        ).json()["request_id"]

        resp = client.post("/evaluations/clear")
        assert resp.status_code == 200
        assert resp.json() == {"deleted_count": 1}

        # Only the active request survives the clear.
        body = client.get("/evaluations").json()
        assert [r["request_id"] for r in body["requests"]] == [active_id]


@pytest_asyncio.fixture
async def repo_and_factory():
    """A repository plus its session factory, so tests can seed rows with
    explicit ``created_at`` values for deterministic ordering assertions."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    factory = create_session_factory(engine)
    yield Repository(factory), factory
    await engine.dispose()


async def _seed_request(factory, *, request_id, game_id, created_at, target_statuses):
    """Insert a request and its targets directly, with explicit timestamps."""
    from eval_service.storage.models import (
        EvaluatedTargetRow,
        EvaluationRequestRow,
    )

    async with factory() as session:
        async with session.begin():
            session.add(
                EvaluationRequestRow(
                    request_id=request_id,
                    game_id=game_id,
                    scope="move",
                    selection_json={"seqs": [1]},
                    force=0,
                    judge_config_json=None,
                    created_at=created_at,
                )
            )
            for seq, status in enumerate(target_statuses, start=1):
                session.add(
                    EvaluatedTargetRow(
                        request_id=request_id,
                        game_id=game_id,
                        target_seq=seq,
                        scope="move",
                        status=status,
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )


def _at(n: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=n)


@pytest.mark.asyncio
async def test_list_evaluations_across_games_newest_first(repo_and_factory):
    repo, factory = repo_and_factory
    await _seed_request(
        factory,
        request_id="r1",
        game_id="g1",
        created_at=_at(1),
        target_statuses=["completed"],
    )
    await _seed_request(
        factory,
        request_id="r2",
        game_id="g2",
        created_at=_at(2),
        target_statuses=["pending"],
    )
    await _seed_request(
        factory,
        request_id="r3",
        game_id="g3",
        created_at=_at(3),
        target_statuses=["running", "completed"],
    )

    rows = await repo.list_requests(limit=50, active_only=False)
    assert [r.request_id for r, _ in rows] == ["r3", "r2", "r1"]
    # Spans multiple games.
    assert {r.game_id for r, _ in rows} == {"g1", "g2", "g3"}


@pytest.mark.asyncio
async def test_list_evaluations_active_only_excludes_terminal(repo_and_factory):
    repo, factory = repo_and_factory
    # All terminal -> excluded under active filter.
    await _seed_request(
        factory,
        request_id="done",
        game_id="g1",
        created_at=_at(1),
        target_statuses=["completed", "skipped", "failed", "cancelled"],
    )
    # Has a running target -> included.
    await _seed_request(
        factory,
        request_id="live",
        game_id="g2",
        created_at=_at(2),
        target_statuses=["completed", "running"],
    )

    active = await repo.list_requests(limit=50, active_only=True)
    assert [r.request_id for r, _ in active] == ["live"]

    everything = await repo.list_requests(limit=50, active_only=False)
    assert {r.request_id for r, _ in everything} == {"done", "live"}


@pytest.mark.asyncio
async def test_list_evaluations_empty_store(repo_and_factory):
    repo, _ = repo_and_factory
    assert await repo.list_requests(limit=50, active_only=False) == []


def test_list_evaluations_endpoint(repo_factory):
    settings = Settings(eval_judge_model="anthropic/claude-x")
    history = FakeHistoryClient({"g1": _game("g1"), "g2": _game("g2")})
    judge = StubJudgeClient()
    with _client(repo_factory, history, judge, settings) as client:
        # Empty store -> {"requests": []}.
        assert client.get("/evaluations").json() == {"requests": []}

        client.post(
            "/games/g1/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        )
        client.post(
            "/games/g2/evaluations",
            json={"scope": "move", "selection": {"seqs": [2]}},
        )

        body = client.get("/evaluations").json()
        assert len(body["requests"]) == 2
        # Cross-game listing carries created_at + per-target summaries.
        item = body["requests"][0]
        assert set(item) == {"request_id", "game_id", "status", "created_at", "targets"}
        assert item["status"] == "pending"
        assert item["targets"][0]["target_seq"] == 2
        assert {r["game_id"] for r in body["requests"]} == {"g1", "g2"}

        # active=true keeps the pending requests; a huge limit is capped.
        active = client.get("/evaluations?active=true&limit=100000").json()
        assert len(active["requests"]) == 2


@pytest.mark.asyncio
async def test_list_evaluations_limit_capped(repo_and_factory):
    from eval_service.api.routers.evaluations import _LIST_LIMIT_CAP

    repo, factory = repo_and_factory
    for i in range(_LIST_LIMIT_CAP + 25):
        await _seed_request(
            factory,
            request_id=f"r{i}",
            game_id=f"g{i}",
            created_at=_at(i),
            target_statuses=["pending"],
        )
    # The route clamps any larger limit down to the cap.
    rows = await repo.list_requests(
        limit=min(_LIST_LIMIT_CAP + 25, _LIST_LIMIT_CAP), active_only=False
    )
    assert len(rows) == _LIST_LIMIT_CAP


class _T:
    """Minimal stand-in carrying just the ``status`` field of a target row."""

    def __init__(self, status: str):
        self.status = status


def test_request_status_aggregation():
    from eval_service.runtime.status import request_status

    # Any non-terminal target -> pending.
    assert request_status([_T("completed"), _T("running")]) == "pending"
    # All succeeded -> completed.
    assert request_status([_T("completed"), _T("completed")]) == "completed"
    # Terminal but none succeeded -> failed.
    assert request_status([_T("skipped"), _T("failed")]) == "failed"
    # Mix of succeeded and skipped/failed -> partial.
    assert request_status([_T("completed"), _T("skipped")]) == "partial"
    # Any cancelled and none failed -> cancelled.
    assert request_status([_T("completed"), _T("cancelled")]) == "cancelled"
    # No targets -> completed (vacuously).
    assert request_status([]) == "completed"
