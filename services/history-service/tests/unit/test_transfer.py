from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from history_service.config import Settings
from history_service.runtime.bundle_codec import MAX_NESTING_DEPTH
from history_service.integrations.game_service import BranchSession
from history_service.runtime.app import create_app
from history_service.runtime.restore import RestoreService
from history_service.runtime.snapshots import SnapshotService
from history_service.schemas.transfer import BUNDLE_FORMAT, BUNDLE_FORMAT_VERSION
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
    """Records what a restore loaded/replayed so two restores can be compared."""

    def __init__(self):
        self.loaded: list[tuple[str, dict]] = []
        self.replayed: list[tuple[str, dict]] = []
        self.created: list[str] = []

    async def create_session(self, plugin_name, *, ephemeral=False):
        self.created.append(plugin_name)
        return BranchSession(
            session_id=f"branch-{len(self.created)}",
            room_slug=f"room-{len(self.created)}",
        )

    async def get_snapshot(self, game_id):
        return {
            "schema_version": 1,
            "plugin_name": "mc",
            "game": {"snapshotOf": game_id},
        }

    async def load_snapshot(self, game_id, snapshot):
        self.loaded.append((game_id, snapshot))
        return {}

    async def replay_action(self, game_id, action):
        self.replayed.append((game_id, action))
        return {}

    async def get_state(self, game_id):
        return {"state": {"mode": "in progress"}}

    async def delete_session(self, game_id):
        return None


class FakeOrchestrator:
    async def restore_session(self, *, game_id, conversation_context, mode):
        return {"session_id": "orch-1"}


def _make_client(*, import_max_bytes: int | None = None):
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    overrides = {"snapshot_every_n_events": 2, "snapshot_max_interval_seconds": 999}
    if import_max_bytes is not None:
        overrides["history_import_max_bytes"] = import_max_bytes
    settings = Settings(**overrides)
    game = FakeGameService()
    orch = FakeOrchestrator()
    return engine, settings, game, orch


@pytest_asyncio.fixture
async def client():
    engine, settings, game, orch = _make_client()
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))
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


@pytest_asyncio.fixture
async def tiny_limit_client():
    """A client whose import ceiling is 64 bytes, to exercise the 413 path."""
    engine, settings, game, orch = _make_client(import_max_bytes=64)
    await ensure_schema(engine)
    repository = Repository(create_session_factory(engine))
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
            yield c
    await engine.dispose()


def _state_envelope(game_id: str, offset: int, *, card: str):
    """A game-service event whose payload embeds a full post-action state."""
    return {
        "game_id": game_id,
        "actor": "game-service",
        "event_type": "game_state",
        "payload": {
            "plugin_name": "mc",
            "status": "in progress",
            "action_path": "actions",
            "action_args": {"type": "move_card", "instance_id": card},
            "state": {"game": {"lastCard": card, "roundNumber": 0}},
        },
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": f"{game_id}:game-service:{offset}",
        "producer_offset": offset,
    }


def _agent_envelope(game_id: str, offset: int):
    return {
        "game_id": game_id,
        "actor": "agent",
        "event_type": "agent_move",
        "payload": {
            "intended_action": "move_card",
            "reasoning": "because",
            "arguments": {"instance_id": "c1"},
            "conversation_context": [{"role": "system", "content": "you play MC"}],
        },
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": f"{game_id}:agent:{offset}",
        "producer_offset": offset,
    }


async def _seed_game(c: httpx.AsyncClient, game_id: str, *, events: int = 5) -> None:
    for offset in range(events):
        envelope = (
            _agent_envelope(game_id, offset)
            if offset % 2
            else _state_envelope(game_id, offset, card=f"c{offset}")
        )
        response = await c.post(f"/games/{game_id}/events", json=envelope)
        assert response.status_code == 200, response.text


def _lines(body: str) -> list[dict]:
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def _bundle(
    *,
    game_id: str = "src",
    events: list[dict] | None = None,
    snapshots: list[dict] | None = None,
    header_overrides: dict | None = None,
    footer_overrides: dict | None = None,
    include_header: bool = True,
    include_footer: bool = True,
) -> bytes:
    """Assemble a bundle by hand so a single field can be made invalid."""
    events = events if events is not None else [_bundle_event(1)]
    snapshots = snapshots or []
    parts: list[str] = []
    if include_header:
        header = {
            "kind": "header",
            "format": BUNDLE_FORMAT,
            "format_version": BUNDLE_FORMAT_VERSION,
            "game_id": game_id,
            "plugin_name": "mc",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "event_count": len(events),
            "snapshot_count": len(snapshots),
        }
        header.update(header_overrides or {})
        parts.append(json.dumps(header))
    parts.extend(json.dumps(event) for event in events)
    parts.extend(json.dumps(snapshot) for snapshot in snapshots)
    if include_footer:
        footer = {
            "kind": "footer",
            "event_count": len(events),
            "snapshot_count": len(snapshots),
        }
        footer.update(footer_overrides or {})
        parts.append(json.dumps(footer))
    return ("\n".join(parts) + "\n").encode()


def _bundle_event(seq: int, **overrides) -> dict:
    event = {
        "kind": "event",
        "seq": seq,
        "event_id": f"e{seq}",
        "envelope_version": 1,
        "actor": "game-service",
        "event_type": "game_state",
        "payload": {"state": {"game": {"n": seq}}, "plugin_name": "mc"},
        "occurred_at": "2026-07-28T10:00:00+00:00",
        "recorded_at": "2026-07-28T10:00:01+00:00",
        "idempotency_key": f"k{seq}",
        "producer_offset": seq,
    }
    event.update(overrides)
    return event


# -- export -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_streams_a_readable_ndjson_bundle(client):
    c, _ = client
    await _seed_game(c, "g1", events=5)

    response = await c.get("/games/g1/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="dragncards-history-g1-full.ndjson"'
    )

    records = _lines(response.text)
    assert records[0]["kind"] == "header"
    assert records[0]["format"] == BUNDLE_FORMAT
    assert records[0]["format_version"] == BUNDLE_FORMAT_VERSION
    assert records[0]["game_id"] == "g1"
    assert records[0]["platform"] == "dragncards"
    assert records[0]["plugin_name"] == "mc"
    assert records[0]["event_count"] == 5
    assert records[-1]["kind"] == "footer"
    assert records[-1]["event_count"] == 5
    assert records[-1]["snapshot_count"] == records[0]["snapshot_count"]

    events = [r for r in records if r["kind"] == "event"]
    assert [e["seq"] for e in events] == [1, 2, 3, 4, 5]
    assert all(
        set(event)
        == {
            "actor",
            "envelope_version",
            "event_id",
            "event_type",
            "idempotency_key",
            "kind",
            "occurred_at",
            "payload",
            "producer_offset",
            "recorded_at",
            "seq",
        }
        for event in events
    )
    # The target game is chosen at import time, so no line carries a game id.
    assert all("game_id" not in e for e in events)
    assert all("platform" not in e for e in events)
    # Payloads survive verbatim.
    assert events[0]["payload"]["state"]["game"]["lastCard"] == "c0"

    snapshots = [r for r in records if r["kind"] == "snapshot"]
    assert snapshots, "the seeded cadence should have produced snapshots"
    assert all(
        set(snapshot) == {"created_at", "kind", "snapshot", "snapshot_at_seq"}
        for snapshot in snapshots
    )
    assert all("platform" not in snapshot for snapshot in snapshots)
    assert [s["snapshot_at_seq"] for s in snapshots] == sorted(
        s["snapshot_at_seq"] for s in snapshots
    )


@pytest.mark.asyncio
async def test_export_keys_are_sorted_so_bundles_diff_cleanly(client):
    c, _ = client
    await _seed_game(c, "g1", events=2)
    body = (await c.get("/games/g1/export")).text
    for line in body.splitlines():
        if not line.strip():
            continue
        keys = list(json.loads(line).keys())
        assert keys == sorted(keys)


@pytest.mark.asyncio
async def test_export_of_unknown_game_is_an_empty_bundle(client):
    c, _ = client
    records = _lines((await c.get("/games/nope/export")).text)
    assert [r["kind"] for r in records] == ["header", "footer"]
    assert records[0]["event_count"] == 0
    assert records[0]["plugin_name"] is None


@pytest.mark.asyncio
async def test_export_rejects_a_malformed_game_id(client):
    c, _ = client
    assert (await c.get("/games/..%2Fetc/export")).status_code in (404, 422)


# -- round trip --------------------------------------------------------------


@pytest.mark.asyncio
async def test_round_trip_export_import_reproduces_the_history(client):
    c, _ = client
    await _seed_game(c, "g1", events=5)

    bundle = (await c.get("/games/g1/export")).content
    imported = await c.post("/import", params={"game_id": "g1copy"}, content=bundle)
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["game_id"] == "g1copy"
    assert body["platform"] == "dragncards"
    assert body["source_game_id"] == "g1"
    assert body["imported_events"] == 5
    assert body["first_seq"] == 1
    assert body["last_seq"] == 5

    original = (await c.get("/games/g1/events?limit=1000")).json()["events"]
    copy = (await c.get("/games/g1copy/events?limit=1000")).json()["events"]
    assert len(copy) == len(original)
    for before, after in zip(original, copy):
        assert after["game_id"] == "g1copy"
        for field in (
            "seq",
            "event_id",
            "envelope_version",
            "actor",
            "event_type",
            "payload",
            "occurred_at",
            "recorded_at",
            "idempotency_key",
            "producer_offset",
        ):
            assert after[field] == before[field], field

    original_snaps = (await c.get("/games/g1/snapshots")).json()["snapshots"]
    copy_snaps = (await c.get("/games/g1copy/snapshots")).json()["snapshots"]
    assert [s["snapshot_at_seq"] for s in copy_snaps] == [
        s["snapshot_at_seq"] for s in original_snaps
    ]
    assert [s["snapshot"] for s in copy_snaps] == [
        s["snapshot"] for s in original_snaps
    ]


@pytest.mark.asyncio
async def test_round_trip_restores_to_an_equivalent_state(client):
    """The imported game reconstructs the same board as the game it came from."""
    c, game = client
    await _seed_game(c, "g1", events=5)
    bundle = (await c.get("/games/g1/export")).content
    assert (
        await c.post("/import", params={"game_id": "g1copy"}, content=bundle)
    ).status_code == 200

    original = await c.post("/games/g1/restore", json={"target_seq": 5, "mode": "new"})
    assert original.status_code == 200, original.text
    loaded_from_original = game.loaded[-1][1]
    replayed_from_original = list(game.replayed)

    copy = await c.post("/games/g1copy/restore", json={"target_seq": 5, "mode": "new"})
    assert copy.status_code == 200, copy.text
    loaded_from_copy = game.loaded[-1][1]

    assert loaded_from_copy == loaded_from_original
    assert original.json()["snapshot_at_seq"] == copy.json()["snapshot_at_seq"]
    assert original.json()["replayed_event_seqs"] == copy.json()["replayed_event_seqs"]
    assert game.replayed[len(replayed_from_original) :] == [
        (copy.json()["game_session_id"], action) for _, action in replayed_from_original
    ]


@pytest.mark.asyncio
async def test_import_defaults_the_target_to_the_bundle_game_id(client):
    c, _ = client
    await _seed_game(c, "g1", events=3)
    bundle = (await c.get("/games/g1/export")).content
    await c.delete("/games/g1")

    imported = await c.post("/import", content=bundle)
    assert imported.status_code == 200, imported.text
    assert imported.json()["game_id"] == "g1"
    assert len((await c.get("/games/g1/events")).json()["events"]) == 3


@pytest.mark.asyncio
async def test_import_reports_the_bundle_platform(client):
    c, _ = client
    bundle = _bundle(header_overrides={"platform": "marvel-lcg"})

    imported = await c.post(
        "/import", params={"game_id": "marvel-copy"}, content=bundle
    )

    assert imported.status_code == 200, imported.text
    assert imported.json()["game_id"] == "marvel-copy"
    assert imported.json()["platform"] == "marvel-lcg"


# -- import rejections -------------------------------------------------------


@pytest.mark.asyncio
async def test_import_rejects_an_existing_target_without_touching_it(client):
    c, _ = client
    await _seed_game(c, "g1", events=3)
    bundle = (await c.get("/games/g1/export")).content

    response = await c.post("/import", content=bundle)
    assert response.status_code == 409
    assert "already has recorded history" in response.json()["detail"]
    # The live game is untouched: still exactly its own three events.
    assert len((await c.get("/games/g1/events")).json()["events"]) == 3


@pytest.mark.asyncio
async def test_import_rejects_unparseable_json_naming_the_line(client):
    c, _ = client
    body = _bundle().replace(b'{"kind": "event"', b'{"kind" "event"', 1)
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "line 2" in response.json()["detail"]
    assert "not valid JSON" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_non_object_line(client):
    c, _ = client
    body = b"[1, 2, 3]\n"
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "expected a JSON object" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_bundle_without_a_header(client):
    c, _ = client
    body = _bundle(include_header=False)
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "must start with a 'header' record" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_an_empty_body(client):
    c, _ = client
    response = await c.post("/import", params={"game_id": "t"}, content=b"")
    assert response.status_code == 400
    assert "no 'header' record" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_foreign_format(client):
    c, _ = client
    body = _bundle(header_overrides={"format": "something-else"})
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "unsupported bundle format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_an_unsupported_format_version(client):
    c, _ = client
    body = _bundle(header_overrides={"format_version": 99})
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "unsupported bundle format_version 99" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_missing_footer_as_truncation(client):
    c, _ = client
    body = _bundle(include_footer=False)
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "truncated" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_footer_counts_that_disagree(client):
    c, _ = client
    body = _bundle(footer_overrides={"event_count": 7})
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "footer declares 7 events but 1 were read" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_seq_gap(client):
    c, _ = client
    body = _bundle(events=[_bundle_event(1), _bundle_event(3)])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "expected 2, got 3" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_seq_that_does_not_start_at_one(client):
    c, _ = client
    body = _bundle(events=[_bundle_event(4)])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "expected 1, got 4" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_snapshots_out_of_order(client):
    c, _ = client

    def snapshot(seq: int) -> dict:
        return {
            "kind": "snapshot",
            "snapshot_at_seq": seq,
            "snapshot": {"schema_version": 1, "plugin_name": "mc", "game": {}},
            "created_at": "2026-07-28T10:00:02+00:00",
        }

    body = _bundle(
        events=[_bundle_event(1), _bundle_event(2), _bundle_event(3)],
        snapshots=[snapshot(2), snapshot(1)],
    )
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "snapshot_at_seq must be ascending" in response.json()["detail"]
    assert (await c.get("/games/t/events")).json()["events"] == []


@pytest.mark.asyncio
async def test_import_rejects_an_unknown_record_kind(client):
    c, _ = client
    body = _bundle(events=[_bundle_event(1, kind="mystery")])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "unknown record kind 'mystery'" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_an_unknown_actor(client):
    c, _ = client
    body = _bundle(events=[_bundle_event(1, actor="attacker")])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "actor" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_an_oversized_field(client):
    c, _ = client
    body = _bundle(events=[_bundle_event(1, event_id="x" * 200)])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "event_id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_bundle_with_no_events(client):
    c, _ = client
    body = _bundle(events=[])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "no events" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_snapshot_beyond_the_last_event(client):
    c, _ = client
    body = _bundle(
        events=[_bundle_event(1)],
        snapshots=[
            {
                "kind": "snapshot",
                "snapshot_at_seq": 9,
                "snapshot": {"schema_version": 1, "plugin_name": "mc", "game": {}},
                "created_at": "2026-07-28T10:00:02+00:00",
            }
        ],
    )
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "beyond the last event seq" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_an_event_after_a_snapshot(client):
    c, _ = client
    snapshot = {
        "kind": "snapshot",
        "snapshot_at_seq": 1,
        "snapshot": {"schema_version": 1, "plugin_name": "mc", "game": {}},
        "created_at": "2026-07-28T10:00:02+00:00",
    }
    body = _bundle(events=[_bundle_event(1)], snapshots=[snapshot]).replace(
        b'{"kind": "footer"',
        json.dumps(_bundle_event(2)).encode() + b'\n{"kind": "footer"',
        1,
    )
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "must precede all snapshots" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_duplicate_events(client):
    c, _ = client
    duplicate = _bundle_event(2, idempotency_key="k1")
    body = _bundle(events=[_bundle_event(1), duplicate])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "duplicate" in response.json()["detail"]
    assert (await c.get("/games/t/events")).json()["events"] == []


@pytest.mark.asyncio
async def test_import_rejects_content_after_the_footer(client):
    c, _ = client
    body = _bundle() + _bundle()
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "after the 'footer' record" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_malformed_target_game_id(client):
    c, _ = client
    response = await c.post(
        "/import", params={"game_id": "../etc/passwd"}, content=_bundle()
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_failed_import_writes_nothing(client):
    """A bundle that breaks partway through leaves no rows behind."""
    c, _ = client
    good = [_bundle_event(seq) for seq in range(1, 4)]
    body = _bundle(events=good).replace(
        json.dumps(_bundle_event(3)).encode(), b'{"kind": "event", "seq": 3}', 1
    )
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert (await c.get("/games/t/events")).json()["events"] == []
    assert (await c.get("/games/t/snapshots")).json()["snapshots"] == []


@pytest.mark.asyncio
async def test_import_rejects_a_body_over_the_ceiling(tiny_limit_client):
    c = tiny_limit_client
    response = await c.post(
        "/import", params={"game_id": "t"}, content=_bundle(events=[_bundle_event(1)])
    )
    assert response.status_code == 413
    assert response.json()["detail"] == "Request body too large"
    assert (await c.get("/games/t/events")).json()["events"] == []


# -- format version 2: blobs -------------------------------------------------

# Big enough to cross the codec's 256-byte extraction threshold, and shaped like
# what a real recording repeats: plugin statics identical on every state, and a
# conversation that every agent move re-ships in full.
_PLUGIN_STATICS = {
    "functions": {f"fn{n}": ["ACTION", f"body-{n}"] for n in range(12)},
    "layout": [[f"cell-{n}" for n in range(12)]],
}
_CONVERSATION = [
    {"role": "system", "content": "you play Marvel Champions. " * 12},
    {"role": "user", "content": "take your turn in game g1. " * 12},
]


def _fat_state_envelope(game_id: str, offset: int, card: str):
    return {
        "game_id": game_id,
        "actor": "game-service",
        "event_type": "game_state",
        "payload": {
            "plugin_name": "mc",
            "status": "in progress",
            "action_path": "actions",
            "action_args": {"type": "move_card", "instance_id": card},
            "state": {
                "game": {"lastCard": card, "roundNumber": 0, **_PLUGIN_STATICS},
                # DragnCards' undo log: event n re-ships every delta before it.
                "deltas": [{"step": s, "pad": "d" * 300} for s in range(offset + 1)],
            },
        },
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": f"{game_id}:game-service:{offset}",
        "producer_offset": offset,
    }


def _fat_agent_envelope(game_id: str, offset: int):
    return {
        "game_id": game_id,
        "actor": "agent",
        "event_type": "agent_move",
        "payload": {
            "intended_action": "move_card",
            "reasoning": "because " * 30,
            "arguments": {"instance_id": "c1", "session_id": game_id},
            "conversation_context": _CONVERSATION,
        },
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": f"{game_id}:agent:{offset}",
        "producer_offset": offset,
    }


async def _seed_repetitive_game(
    c: httpx.AsyncClient, game_id: str, *, events: int = 8
) -> None:
    for offset in range(events):
        envelope = (
            _fat_agent_envelope(game_id, offset)
            if offset % 2
            else _fat_state_envelope(game_id, offset, card=f"c{offset}")
        )
        response = await c.post(f"/games/{game_id}/events", json=envelope)
        assert response.status_code == 200, response.text


async def _stored(c: httpx.AsyncClient, game_id: str) -> tuple[list, list]:
    events = (await c.get(f"/games/{game_id}/events?limit=1000")).json()["events"]
    snapshots = (await c.get(f"/games/{game_id}/snapshots")).json()["snapshots"]
    return events, snapshots


@pytest.mark.asyncio
async def test_export_carries_repeated_values_once(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=8)

    body = (await c.get("/games/g1/export")).text
    records = _lines(body)
    blobs = [r for r in records if r["kind"] == "blob"]
    assert blobs, "a repetitive game should extract blobs"
    assert records[-1]["blob_count"] == len(blobs)

    # The plugin's static definitions appear exactly once in the whole file.
    functions = json.dumps(_PLUGIN_STATICS["functions"], sort_keys=True)[1:-1]
    assert body.count(functions) == 1
    # Every event line is small enough to read, and still says what it is: the
    # payload's own keys stay on the record's line and only its bulky members
    # become references.
    events = [line for line in body.splitlines() if '"kind": "event"' in line]
    assert len(events) == 8
    assert max(len(line) for line in events) < 1024
    assert '"payload": {"$ref"' not in body
    assert all(
        ('"action_path": "actions"' in line) == ('"game_state"' in line)
        for line in events
    )

    # Blob ids are assigned in first-encounter order and each names where it
    # was first seen, so a reference can be chased by grep.
    assert [b["id"] for b in blobs] == [f"b{n}" for n in range(1, len(blobs) + 1)]
    assert all(b["first_seen"].startswith(("event[", "snapshot[")) for b in blobs)


@pytest.mark.asyncio
async def test_bundle_size_grows_with_new_content_not_with_repetition(client):
    """The property that makes the file small: repeats are not re-shipped.

    Doubling a repetitive game's length roughly doubles what a verbatim bundle
    would carry, because every state re-ships the whole delta log and every
    agent move the whole conversation. The deduplicated bundle grows by the new
    content only.
    """
    c, _ = client
    await _seed_repetitive_game(c, "short", events=8)
    await _seed_repetitive_game(c, "long", events=16)

    def measure(records):
        table = {b["id"]: b["value"] for b in records if b["kind"] == "blob"}

        def expand(value):
            if isinstance(value, dict):
                if list(value) == ["$ref"]:
                    return expand(table[value["$ref"]])
                return {k: expand(v) for k, v in value.items()}
            if isinstance(value, list):
                return [expand(v) for v in value]
            return value

        deduplicated = sum(len(json.dumps(r)) for r in records)
        verbatim = sum(
            len(json.dumps(expand(r))) for r in records if r["kind"] != "blob"
        )
        return deduplicated, verbatim

    short = measure(_lines((await c.get("/games/short/export")).text))
    long = measure(_lines((await c.get("/games/long/export")).text))
    short_dedup, short_verbatim = short
    long_dedup, long_verbatim = long

    assert short_dedup < short_verbatim
    assert long_dedup < long_verbatim
    # Bytes per event: the verbatim cost of an event rises as the history it
    # re-ships grows, while the deduplicated cost does not.
    assert long_verbatim / 16 > short_verbatim / 8
    assert long_dedup / 16 <= short_dedup / 8


@pytest.mark.asyncio
async def test_two_exports_differ_only_in_the_export_timestamp(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=6)
    first = _lines((await c.get("/games/g1/export")).text)
    second = _lines((await c.get("/games/g1/export")).text)
    for record in (first[0], second[0]):
        record.pop("exported_at")
    assert first == second


@pytest.mark.asyncio
async def test_round_trip_of_a_repetitive_game_reproduces_every_payload(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=8)

    bundle = (await c.get("/games/g1/export")).content
    imported = await c.post("/import", params={"game_id": "g1copy"}, content=bundle)
    assert imported.status_code == 200, imported.text
    assert imported.json()["mode"] == "full"

    original_events, original_snaps = await _stored(c, "g1")
    copy_events, copy_snaps = await _stored(c, "g1copy")
    assert [e["payload"] for e in copy_events] == [
        e["payload"] for e in original_events
    ]
    assert [s["snapshot"] for s in copy_snaps] == [
        s["snapshot"] for s in original_snaps
    ]


@pytest.mark.asyncio
async def test_export_import_export_is_byte_identical_in_full_mode(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=8)
    first = (await c.get("/games/g1/export")).content
    assert (
        await c.post("/import", params={"game_id": "g1copy"}, content=first)
    ).status_code == 200
    second = (await c.get("/games/g1copy/export")).content

    before, after = _lines(first.decode()), _lines(second.decode())
    # The header names the game it was exported from and when; nothing else may
    # move between a round trip's two exports.
    for record in (before[0], after[0]):
        record.pop("exported_at")
        record.pop("game_id")
    assert before == after


@pytest.mark.asyncio
async def test_a_payload_containing_the_reference_markers_round_trips(client):
    c, _ = client
    tricky = {"$ref": "not-a-reference", "note": "x"}
    await c.post(
        "/games/g1/events",
        json={
            "game_id": "g1",
            "actor": "game-service",
            "event_type": "game_state",
            "payload": {
                "plugin_name": "mc",
                "state": {
                    "game": {"marker": {"$ref": "b1"}, "escaped": {"$literal": tricky}},
                    "pad": "p" * 400,
                },
            },
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "idempotency_key": "g1:game-service:0",
            "producer_offset": 0,
        },
    )
    bundle = (await c.get("/games/g1/export")).content
    assert (
        await c.post("/import", params={"game_id": "g1copy"}, content=bundle)
    ).status_code == 200
    original, _ = await _stored(c, "g1")
    copy, _ = await _stored(c, "g1copy")
    assert copy[0]["payload"] == original[0]["payload"]
    assert copy[0]["payload"]["state"]["game"]["marker"] == {"$ref": "b1"}


@pytest.mark.asyncio
async def test_import_rejects_a_blob_in_a_version_1_bundle(client):
    c, _ = client
    body = _bundle(
        header_overrides={"format_version": 1},
        footer_overrides={"blob_count": 1},
    ).replace(
        b'{"kind": "event"',
        b'{"kind": "blob", "id": "b1", "first_seen": "x", "value": {"a": 1}}\n'
        b'{"kind": "event"',
        1,
    )
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "version 1 bundle" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_version_1_bundle_still_imports(client):
    """Nothing a user exported before this format existed stops working."""
    c, _ = client
    body = _bundle(game_id="legacy", header_overrides={"format_version": 1})
    response = await c.post("/import", content=body)
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "full"
    assert response.json()["game_id"] == "legacy"
    events, _ = await _stored(c, "legacy")
    assert [e["seq"] for e in events] == [1]


@pytest.mark.asyncio
async def test_import_rejects_a_footer_blob_count_mismatch(client):
    c, _ = client
    body = _bundle(footer_overrides={"blob_count": 3})
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "declares 3 blobs but 0 were read" in response.json()["detail"]


@pytest.mark.asyncio
async def test_import_rejects_a_dangling_reference(client):
    c, _ = client
    event = _bundle_event(1, payload={"state": {"$ref": "b9"}})
    body = _bundle(events=[event])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "unknown blob 'b9'" in response.json()["detail"]
    assert (await c.get("/games/t/events")).json()["events"] == []


@pytest.mark.asyncio
async def test_import_refuses_a_reference_bomb(tiny_limit_client):
    """Small on disk, enormous once expanded."""
    c = tiny_limit_client
    blobs = [
        {"kind": "blob", "id": "b1", "first_seen": "x", "value": {"pad": "y" * 200}}
    ]
    for index in range(2, 20):
        blobs.append(
            {
                "kind": "blob",
                "id": f"b{index}",
                "first_seen": "x",
                "value": [{"$ref": f"b{index - 1}"}, {"$ref": f"b{index - 1}"}],
            }
        )
    parts = [
        json.dumps(
            {
                "kind": "header",
                "format": BUNDLE_FORMAT,
                "format_version": BUNDLE_FORMAT_VERSION,
                "game_id": "src",
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "event_count": 1,
                "snapshot_count": 0,
            }
        )
    ]
    parts.extend(json.dumps(blob) for blob in blobs)
    parts.append(json.dumps(_bundle_event(1, payload={"state": {"$ref": "b19"}})))
    parts.append(
        json.dumps(
            {
                "kind": "footer",
                "event_count": 1,
                "snapshot_count": 0,
                "blob_count": len(blobs),
            }
        )
    )
    body = ("\n".join(parts) + "\n").encode()

    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 413
    assert (await c.get("/games/t/events")).json()["events"] == []


# -- export modes ------------------------------------------------------------


@pytest.mark.asyncio
async def test_minimal_omits_exactly_the_prompt_material(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=8)

    full = _lines((await c.get("/games/g1/export?mode=full")).text)
    minimal_response = await c.get("/games/g1/export?mode=minimal")
    minimal = _lines(minimal_response.text)

    assert full[0]["mode"] == "full"
    assert full[0]["omitted_payload_fields"] == []
    assert minimal[0]["mode"] == "minimal"
    assert minimal[0]["omitted_payload_fields"] == ["agent_move.conversation_context"]
    assert (
        minimal_response.headers["content-disposition"]
        == 'attachment; filename="dragncards-history-g1-minimal.ndjson"'
    )

    # Same records, same seqs, same snapshots.
    assert [r["kind"] for r in full if r["kind"] != "blob"] == [
        r["kind"] for r in minimal if r["kind"] != "blob"
    ]

    def payloads(records, table):
        def expand(value):
            if isinstance(value, dict):
                if list(value) == ["$ref"]:
                    return expand(table[value["$ref"]])
                return {k: expand(v) for k, v in value.items()}
            if isinstance(value, list):
                return [expand(v) for v in value]
            return value

        return [expand(r["payload"]) for r in records if r["kind"] == "event"]

    full_payloads = payloads(
        full, {b["id"]: b["value"] for b in full if b["kind"] == "blob"}
    )
    minimal_payloads = payloads(
        minimal, {b["id"]: b["value"] for b in minimal if b["kind"] == "blob"}
    )
    for before, after in zip(full_payloads, minimal_payloads):
        expected = {k: v for k, v in before.items() if k != "conversation_context"}
        assert after == expected
        # Elision is by absence, never by an empty value.
        assert "conversation_context" not in after

    assert any("conversation_context" in p for p in full_payloads)
    assert minimal_response.text.count("conversation_context") == 1  # the header


@pytest.mark.asyncio
async def test_minimal_round_trip_loses_exactly_the_conversation(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=8)

    bundle = (await c.get("/games/g1/export?mode=minimal")).content
    imported = await c.post("/import", params={"game_id": "g1min"}, content=bundle)
    assert imported.status_code == 200, imported.text
    assert imported.json()["mode"] == "minimal"

    original, original_snaps = await _stored(c, "g1")
    copy, copy_snaps = await _stored(c, "g1min")
    assert [s["snapshot"] for s in copy_snaps] == [
        s["snapshot"] for s in original_snaps
    ]
    for before, after in zip(original, copy):
        assert after["payload"] == {
            k: v for k, v in before["payload"].items() if k != "conversation_context"
        }

    # Re-exporting the imported game reports 'full' honestly: the recording has
    # no prompts, rather than prompts that were empty.
    again = _lines((await c.get("/games/g1min/export")).text)
    assert again[0]["mode"] == "full"
    assert again[0]["omitted_payload_fields"] == []
    assert '"conversation_context"' not in json.dumps(again)


@pytest.mark.asyncio
async def test_restoring_a_minimally_imported_game_reports_the_missing_context(client):
    """The trap: an empty conversation must not pass as a restored one."""
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=8)
    bundle = (await c.get("/games/g1/export?mode=minimal")).content
    assert (
        await c.post("/import", params={"game_id": "g1min"}, content=bundle)
    ).status_code == 200

    full_restore = await c.post(
        "/games/g1/restore", json={"target_seq": 8, "mode": "new"}
    )
    assert full_restore.json()["agent_context_restored"] is True

    minimal_restore = await c.post(
        "/games/g1min/restore", json={"target_seq": 8, "mode": "new"}
    )
    assert minimal_restore.status_code == 200, minimal_restore.text
    body = minimal_restore.json()
    # The game state still restores; only the conversation is reported missing.
    assert body["replayed_event_seqs"] == full_restore.json()["replayed_event_seqs"]
    assert body["agent_context_restored"] is False
    assert "minimal" in body["agent_context_note"]


@pytest.mark.asyncio
async def test_an_unknown_export_mode_is_refused(client):
    c, _ = client
    await _seed_game(c, "g1", events=2)
    assert (await c.get("/games/g1/export?mode=tiny")).status_code == 422


@pytest.mark.asyncio
async def test_import_rejects_a_full_header_that_declares_omitted_fields(client):
    c, _ = client
    body = _bundle(header_overrides={"mode": "full", "omitted_payload_fields": ["a.b"]})
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "contradict" in response.json()["detail"]


# -- import as ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_as_new_never_conflicts_with_the_source(client):
    c, _ = client
    await _seed_repetitive_game(c, "g1", events=6)
    bundle = (await c.get("/games/g1/export")).content

    first = await c.post("/import", params={"as_new": "true"}, content=bundle)
    second = await c.post("/import", params={"as_new": "true"}, content=bundle)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    for response in (first, second):
        assert response.json()["source_game_id"] == "g1"
        assert response.json()["game_id"] != "g1"
    assert first.json()["game_id"] != second.json()["game_id"]

    # The source is untouched and each copy holds the same history.
    original, _ = await _stored(c, "g1")
    for response in (first, second):
        copy, _ = await _stored(c, response.json()["game_id"])
        assert [e["payload"] for e in copy] == [e["payload"] for e in original]


@pytest.mark.asyncio
async def test_naming_a_target_and_asking_for_a_new_one_is_refused(client):
    c, _ = client
    await _seed_game(c, "g1", events=2)
    bundle = (await c.get("/games/g1/export")).content
    response = await c.post(
        "/import", params={"game_id": "somewhere", "as_new": "true"}, content=bundle
    )
    assert response.status_code == 400
    assert "as_new" in response.json()["detail"]
    assert "somewhere" in response.json()["detail"]
    assert (await c.get("/games/somewhere/events")).json()["events"] == []


@pytest.mark.asyncio
async def test_the_conflict_names_the_alternatives(client):
    c, _ = client
    await _seed_game(c, "g1", events=2)
    bundle = (await c.get("/games/g1/export")).content
    response = await c.post("/import", content=bundle)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "as_new=true" in detail
    assert "game_id" in detail


@pytest.mark.asyncio
async def test_remaining_references_to_the_source_game_are_counted(client):
    c, _ = client
    # Every agent move records `arguments.session_id`, which is the source id.
    await _seed_repetitive_game(c, "g1", events=8)
    bundle = (await c.get("/games/g1/export")).content

    copied = await c.post("/import", params={"as_new": "true"}, content=bundle)
    assert copied.status_code == 200, copied.text
    agent_events = [
        e
        for e in (await c.get("/games/g1/events?limit=1000")).json()["events"]
        if e["actor"] == "agent"
    ]
    assert copied.json()["source_id_references"] == len(agent_events)

    # Onto its own id the references are current, not stale.
    await c.delete("/games/g1")
    same = await c.post("/import", content=bundle)
    assert same.status_code == 200, same.text
    assert same.json()["game_id"] == "g1"
    assert same.json()["source_id_references"] == 0


@pytest.mark.asyncio
async def test_a_version_1_bundle_also_reports_its_source_references(client):
    """The count is about provenance, not about the format that carried it."""
    c, _ = client
    event = _bundle_event(1, payload={"arguments": {"session_id": "legacy"}})
    body = _bundle(
        game_id="legacy", events=[event], header_overrides={"format_version": 1}
    )
    response = await c.post("/import", params={"as_new": "true"}, content=body)
    assert response.status_code == 200, response.text
    assert response.json()["source_id_references"] == 1


@pytest.mark.asyncio
async def test_import_rejects_a_bundle_that_nests_past_the_limit(client):
    """A hand-built file must not pick how deep this process recurses."""
    c, _ = client
    payload: dict = {"leaf": 1}
    for _ in range(MAX_NESTING_DEPTH + 5):
        payload = {"deeper": payload}
    body = _bundle(events=[_bundle_event(1, payload=payload)])
    response = await c.post("/import", params={"game_id": "t"}, content=body)
    assert response.status_code == 400
    assert "nests deeper" in response.json()["detail"]
    assert (await c.get("/games/t/events")).json()["events"] == []
