from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from history_service.config import Settings
from history_service.runtime.app import create_app
from history_service.runtime.restore import RestoreService
from history_service.runtime.snapshots import SnapshotService
from history_service.storage.db import create_session_factory
from history_service.storage.migrations import ensure_schema
from history_service.storage.repository import Repository


class FakeValkey:
    async def execute(self, *parts):
        if str(parts[0]).upper() == "PING":
            return "PONG"
        return None

    async def aclose(self):
        return None


class FakeGameService:
    def __init__(self):
        self.loaded = []
        self.replayed = []
        self.created = []
        self.created_ephemeral = []

    async def create_session(self, plugin_name, *, ephemeral=False):
        self.created.append(plugin_name)
        self.created_ephemeral.append(ephemeral)
        return f"branch-{len(self.created)}"

    async def get_snapshot(self, game_id):
        return {"schema_version": 1, "plugin_name": "p", "game": {}}

    async def load_snapshot(self, game_id, snapshot):
        self.loaded.append((game_id, snapshot))
        return {}

    async def replay_action(self, game_id, action):
        self.replayed.append((game_id, action))
        return {}

    async def get_state(self, game_id):
        return {"state": {"mode": "in progress"}}


class FakeOrchestrator:
    async def restore_session(self, *, game_id, conversation_context, mode):
        return {"session_id": "orch-1"}


def _envelope(game_id, actor, offset, **payload):
    return {
        "game_id": game_id,
        "actor": actor,
        "event_type": "state",
        "payload": payload,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": f"{game_id}:{actor}:{offset}",
        "producer_offset": offset,
    }


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))
    game = FakeGameService()
    orch = FakeOrchestrator()
    settings = Settings(snapshot_every_n_events=2, snapshot_max_interval_seconds=999)
    app = create_app(
        settings=settings,
        repository=repository,
        valkey=FakeValkey(),
        game_service_client=game,
        orchestrator_client=orch,
        snapshot_service=SnapshotService(
            settings=settings, repository=repository, game_service=game
        ),
        restore_service=RestoreService(
            repository=repository, game_service=game, orchestrator=orch
        ),
        start_ingester=False,
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c, game
    await engine.dispose()


@pytest.mark.asyncio
async def test_health_and_ready(client):
    c, _ = client
    assert (await c.get("/health")).json() == {"status": "ok"}
    ready = (await c.get("/ready")).json()
    assert ready["checks"]["database"] is True
    assert ready["checks"]["valkey"] is True
    # No secret values leak into readiness output.
    assert "password" not in str(ready).lower()


@pytest.mark.asyncio
async def test_backfill_and_read_events(client):
    c, _ = client
    for offset in range(3):
        resp = await c.post(
            "/games/g1/events", json=_envelope("g1", "game-service", offset)
        )
        assert resp.status_code == 200
        assert resp.json()["seq"] == offset + 1

    listing = (await c.get("/games/g1/events")).json()
    assert [e["seq"] for e in listing["events"]] == [1, 2, 3]


@pytest.mark.asyncio
async def test_user_prompt_event_accepted_stored_and_listed(client):
    c, _ = client
    body = {
        **_envelope("g1", "user", 0),
        "event_type": "user_prompt",
        "payload": {"prompt": "play Ms. Marvel"},
    }
    resp = await c.post("/games/g1/events", json=body)
    assert resp.status_code == 200
    assert resp.json()["inserted"] is True

    listing = (await c.get("/games/g1/events")).json()["events"]
    assert len(listing) == 1
    stored = listing[0]
    assert stored["actor"] == "user"
    assert stored["event_type"] == "user_prompt"
    assert stored["payload"] == {"prompt": "play Ms. Marvel"}


@pytest.mark.asyncio
async def test_user_prompt_event_is_not_replayed_during_restore(client):
    c, game = client
    # A user_prompt interleaved with a real game-service mutation must NOT be
    # replayed as a game action during restore (it is not game-mutating).
    await c.post(
        "/games/g1/events",
        json=_envelope("g1", "game-service", 0, status="in progress"),
    )
    await c.post(
        "/games/g1/events",
        json={
            **_envelope("g1", "user", 1),
            "event_type": "user_prompt",
            "payload": {"prompt": "draw a card"},
        },
    )
    await c.post(
        "/games/g1/events",
        json={
            **_envelope("g1", "game-service", 2, status="in progress"),
            "event_type": "action",
            "payload": {
                "action_path": "draw_card",
                "action_args": {},
                "status": "in progress",
            },
        },
    )

    resp = await c.post("/games/g1/restore", json={"target_seq": 3, "mode": "new"})
    assert resp.status_code == 200
    body = resp.json()
    # Only the game-service mutating action (seq 3) is replayed; the user_prompt
    # (seq 2) is skipped entirely.
    assert body["replayed_event_seqs"] == [3]
    assert all(action.get("action_path") for _, action in game.replayed)


@pytest.mark.asyncio
async def test_backfill_duplicate_idempotent(client):
    c, _ = client
    body = _envelope("g1", "game-service", 0)
    first = (await c.post("/games/g1/events", json=body)).json()
    dup = (await c.post("/games/g1/events", json=body)).json()
    assert first["inserted"] is True
    assert dup["inserted"] is False
    assert dup["seq"] == first["seq"]


@pytest.mark.asyncio
async def test_backfill_triggers_snapshot(client):
    c, game = client
    await c.post("/games/g1/events", json=_envelope("g1", "game-service", 0))
    await c.post("/games/g1/events", json=_envelope("g1", "game-service", 1))
    snapshots = (await c.get("/games/g1/snapshots")).json()
    assert len(snapshots["snapshots"]) == 1
    assert snapshots["snapshots"][0]["snapshot_at_seq"] == 2


@pytest.mark.asyncio
async def test_unknown_game_returns_empty(client):
    c, _ = client
    assert (await c.get("/games/missing/events")).json()["events"] == []
    assert (await c.get("/games/missing/snapshots")).json()["snapshots"] == []


@pytest.mark.asyncio
async def test_list_games_empty(client):
    c, _ = client
    assert (await c.get("/games")).json() == {"games": []}


@pytest.mark.asyncio
async def test_list_games_counts_and_ordering(client):
    c, _ = client
    for offset in range(2):
        await c.post("/games/g1/events", json=_envelope("g1", "game-service", offset))
    await c.post("/games/g2/events", json=_envelope("g2", "game-service", 0))

    body = (await c.get("/games")).json()
    # Ordered by last_recorded_at DESC: g2 recorded most recently.
    assert [g["game_id"] for g in body["games"]] == ["g2", "g1"]
    by_id = {g["game_id"]: g for g in body["games"]}
    assert by_id["g1"]["event_count"] == 2
    assert by_id["g2"]["event_count"] == 1
    assert by_id["g1"]["first_recorded_at"] is not None
    assert by_id["g1"]["last_recorded_at"] is not None


@pytest.mark.asyncio
async def test_delete_game_removes_events_and_snapshots(client):
    c, _ = client
    # Two events trigger one snapshot at seq 2 (cadence=2).
    await c.post("/games/g1/events", json=_envelope("g1", "game-service", 0))
    await c.post("/games/g1/events", json=_envelope("g1", "game-service", 1))
    assert len((await c.get("/games/g1/snapshots")).json()["snapshots"]) == 1

    resp = await c.request("DELETE", "/games/g1")
    assert resp.status_code == 200
    assert resp.json() == {
        "game_id": "g1",
        "deleted_events": 2,
        "deleted_snapshots": 1,
    }
    assert (await c.get("/games/g1/events")).json()["events"] == []
    assert (await c.get("/games/g1/snapshots")).json()["snapshots"] == []
    assert (await c.get("/games")).json() == {"games": []}


@pytest.mark.asyncio
async def test_delete_absent_game_is_idempotent(client):
    c, _ = client
    resp = await c.request("DELETE", "/games/missing")
    assert resp.status_code == 200
    assert resp.json() == {
        "game_id": "missing",
        "deleted_events": 0,
        "deleted_snapshots": 0,
    }


@pytest.mark.asyncio
async def test_restore_endpoint(client):
    c, _ = client
    await c.post(
        "/games/g1/events",
        json=_envelope("g1", "game-service", 0, status="in progress"),
    )
    await c.post(
        "/games/g1/events",
        json={
            **_envelope("g1", "game-service", 1, status="in progress"),
            "event_type": "action",
            "payload": {
                "action_path": "draw_card",
                "action_args": {},
                "status": "in progress",
            },
        },
    )
    # A snapshot is taken at seq 2 (cadence=2), so restoring to seq 2 loads the
    # nearest snapshot and needs no forward replay.
    resp = await c.post("/games/g1/restore", json={"target_seq": 2, "mode": "new"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "restored"
    assert body["target_seq"] == 2
    assert body["mode"] == "new"
    assert body["snapshot_at_seq"] == 2
    assert body["replayed_event_seqs"] == []
    # A fresh real game-service session was created for the branch.
    assert body["session_id"] == body["game_session_id"]
    assert body["game_session_id"].startswith("branch-")


@pytest.mark.asyncio
async def test_restore_endpoint_ephemeral_flag_threaded(client):
    c, game = client
    await c.post(
        "/games/g1/events",
        json=_envelope("g1", "game-service", 0, status="in progress"),
    )
    await c.post(
        "/games/g1/events",
        json={
            **_envelope("g1", "game-service", 1, status="in progress"),
            "event_type": "action",
            "payload": {
                "action_path": "draw_card",
                "action_args": {},
                "status": "in progress",
            },
        },
    )
    resp = await c.post(
        "/games/g1/restore",
        json={"target_seq": 2, "mode": "new", "ephemeral": True},
    )
    assert resp.status_code == 200
    # The game-service branch session was created with ephemeral=True.
    assert game.created_ephemeral == [True]


@pytest.mark.asyncio
async def test_restore_out_of_range_returns_400(client):
    c, _ = client
    await c.post("/games/g1/events", json=_envelope("g1", "game-service", 0))
    resp = await c.post("/games/g1/restore", json={"target_seq": 99, "mode": "new"})
    assert resp.status_code == 400


# Ids that violate the character class (but contain no slash) reach the route
# and are rejected by the Path(pattern=...) constraint with a 422.
@pytest.mark.parametrize("bad_id", ["with space", "x" * 65, "bad.id", "a:b", "a;b"])
@pytest.mark.asyncio
async def test_malformed_game_id_rejected_with_422(client, bad_id):
    c, _ = client
    # Every game-scoped route validates game_id at the boundary, so a malformed
    # id is rejected before any DB or outbound call.
    assert (await c.get(f"/games/{bad_id}/events")).status_code == 422
    assert (await c.get(f"/games/{bad_id}/snapshots")).status_code == 422
    assert (await c.request("DELETE", f"/games/{bad_id}")).status_code == 422
    assert (
        await c.post(f"/games/{bad_id}/restore", json={"target_seq": 1, "mode": "new"})
    ).status_code == 422
    assert (
        await c.post(
            f"/games/{bad_id}/events", json=_envelope(bad_id, "game-service", 0)
        )
    ).status_code == 422


# Slash / encoded-slash ids never match the single-segment route, so they are
# rejected before the handler too (route miss => 404, or 422 if matched).
@pytest.mark.parametrize("bad_id", ["..%2F..%2Fetc", "a%2Fb", "x" * 200])
@pytest.mark.asyncio
async def test_traversal_game_id_never_reaches_handler(client, bad_id):
    c, _ = client
    assert (await c.get(f"/games/{bad_id}/events")).status_code in (404, 422)
    assert (await c.request("DELETE", f"/games/{bad_id}")).status_code in (404, 422)


@pytest.mark.asyncio
async def test_well_formed_unknown_id_still_idempotent_delete(client):
    c, _ = client
    # A valid-but-absent id keeps the idempotent delete semantics (200, zero counts).
    resp = await c.request("DELETE", "/games/well-formed_unknown-123")
    assert resp.status_code == 200
    assert resp.json() == {
        "game_id": "well-formed_unknown-123",
        "deleted_events": 0,
        "deleted_snapshots": 0,
    }
