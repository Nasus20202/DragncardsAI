"""
Integration tests for the FastAPI HTTP REST API.

Requires a running DragnCards instance with the Marvel Champions plugin installed.

Run with:
    pytest tests/integration/test_api.py -v

Note: Tests that call endpoints which invoke WebSocket operations (execute_action,
get_state) must use httpx.AsyncClient with the ASGI transport to avoid blocking
the asyncio event loop (which would prevent the WebSocket receiver task from running).
Tests that only need synchronous HTTP (health, list, 404 checks) use TestClient.
"""

import os

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

pytestmark = pytest.mark.live

from game_service.api.app import create_app
from game_service.logic.session_manager import SessionManager
from game_service.mcp.server import create_mcp_server

DRAGNCARDS_HTTP_URL = os.environ.get("DRAGNCARDS_HTTP_URL", "http://localhost:4000")
DRAGNCARDS_WS_URL = os.environ.get("DRAGNCARDS_WS_URL", "ws://localhost:4000/socket")
DEV_USER_EMAIL = os.environ.get("DEV_USER_EMAIL", "dev_user@example.com")
DEV_USER_PASSWORD = os.environ.get("DEV_USER_PASSWORD", "password")

PLUGIN_REGISTRY = {
    "marvel-champions": {
        "id": int(os.environ.get("MC_PLUGIN_ID", "1")),
        "version": int(os.environ.get("MC_PLUGIN_VERSION", "3")),
        "name": "Marvel Champions",
    }
}


@pytest.fixture
def manager():
    return SessionManager(
        dragncards_http_url=DRAGNCARDS_HTTP_URL,
        dragncards_ws_url=DRAGNCARDS_WS_URL,
        email=DEV_USER_EMAIL,
        password=DEV_USER_PASSWORD,
        plugin_registry=PLUGIN_REGISTRY,
    )


@pytest.fixture
def app(manager):
    return create_app(session_manager=manager)


@pytest.fixture
def mcp(manager, app):
    return create_mcp_server(session_manager=manager, fastapi_app=app)


@pytest.fixture
def sync_client(app):
    """Synchronous TestClient — use only for endpoints that don't touch WebSocket."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Health check  (sync safe — no WebSocket)
# ---------------------------------------------------------------------------


def test_health(sync_client):
    """GET /health returns 200 ok."""
    resp = sync_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /games  (sync safe — just reads in-memory list)
# ---------------------------------------------------------------------------


def test_list_games_empty(sync_client):
    """GET /games on a fresh manager returns an empty list."""
    resp = sync_client.get("/games")
    assert resp.status_code == 200
    assert resp.json() == {"sessions": []}


def test_list_card_providers(sync_client):
    """GET /card-providers returns the available game plugin catalog."""
    resp = sync_client.get("/card-providers")
    assert resp.status_code == 200
    body = resp.json()
    assert "providers" in body
    assert any(
        provider["provider"] == "marvel-champions" for provider in body["providers"]
    )


@pytest.mark.asyncio
async def test_list_games_with_session(app, manager):
    """GET /games lists the active session."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/games")
        assert resp.status_code == 200
        ids = [s["session_id"] for s in resp.json()["sessions"]]
        assert session.session_id in ids
    finally:
        await manager.delete_session(session.session_id)


# ---------------------------------------------------------------------------
# POST /games
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_game(app, manager):
    """POST /games creates a session and returns metadata."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/games", json={"plugin_name": "marvel-champions"})
    assert resp.status_code == 201
    body = resp.json()
    assert "session" in body
    session = body["session"]
    assert "session_id" in session
    assert session["plugin_name"] == "marvel-champions"
    assert "room_slug" in session
    assert "created_at" in session
    assert "frontend_url" in session
    # Cleanup
    await manager.delete_session(session["session_id"])


@pytest.mark.asyncio
async def test_create_game_unknown_plugin(app):
    """POST /games with an unknown plugin returns 400."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/games", json={"plugin_name": "nonexistent-plugin"})
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_attach_game_shares_room_state(app, manager):
    """POST /games/attach joins an existing room and sees shared state."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        create_resp = await client.post(
            "/games", json={"plugin_name": "marvel-champions"}
        )
        assert create_resp.status_code == 201
        primary_session_id = create_resp.json()["session"]["session_id"]
        room_slug = create_resp.json()["session"]["room_slug"]

        attached_session_id = None
        try:
            attach_resp = await client.post(
                "/games/attach",
                json={
                    "plugin_name": "marvel-champions",
                    "room_slug": room_slug,
                },
            )
            assert attach_resp.status_code == 201
            attached_session_id = attach_resp.json()["session"]["session_id"]
            assert attached_session_id != primary_session_id

            action_resp = await client.post(
                f"/games/{primary_session_id}/actions",
                json={"type": "next_step"},
            )
            assert action_resp.status_code == 200

            state_resp = await client.get(f"/games/{attached_session_id}/state")
            assert state_resp.status_code == 200
            expected_step_id = state_resp.json()["state"]["game"]["stepId"]

            primary_state_resp = await client.get(f"/games/{primary_session_id}/state")
            assert primary_state_resp.status_code == 200
            assert (
                primary_state_resp.json()["state"]["game"]["stepId"] == expected_step_id
            )
        finally:
            if attached_session_id is not None:
                await manager.delete_session(attached_session_id)
            await manager.delete_session(primary_session_id)


# ---------------------------------------------------------------------------
# GET /games/{id}/state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_game_state(app, manager):
    """GET /games/{id}/state returns the current game state."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/games/{session.session_id}/state")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["state"] is not None
        assert "game" in body["state"]
    finally:
        await manager.delete_session(session.session_id)


def test_get_game_state_not_found(sync_client):
    """GET /games/{id}/state with unknown ID returns 404."""
    resp = sync_client.get("/games/00000000-0000-0000-0000-000000000000/state")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_snapshot_export_and_load_round_trip(app, manager):
    """Exporting a snapshot and loading it back restores the mutated state."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            export_resp = await client.get(f"/games/{session.session_id}/snapshot")
            assert export_resp.status_code == 200
            snapshot = export_resp.json()
            assert snapshot["plugin_name"] == "marvel-champions"

            mutated = dict(snapshot)
            mutated["game"] = dict(snapshot["game"])
            mutated["game"]["roundNumber"] = 13

            load_resp = await client.put(
                f"/games/{session.session_id}/snapshot",
                json=mutated,
            )
            assert load_resp.status_code == 200
            assert load_resp.json()["state"]["game"]["roundNumber"] == 13

            state_resp = await client.get(f"/games/{session.session_id}/state")
            assert state_resp.status_code == 200
            assert state_resp.json()["state"]["game"]["roundNumber"] == 13
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_snapshot_load_rejects_plugin_mismatch(app, manager):
    """Loading a snapshot for another plugin returns HTTP 400 and does not mutate."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            export_resp = await client.get(f"/games/{session.session_id}/snapshot")
            assert export_resp.status_code == 200
            snapshot = export_resp.json()
            snapshot["plugin_name"] = "other-game"

            load_resp = await client.put(
                f"/games/{session.session_id}/snapshot",
                json=snapshot,
            )
            assert load_resp.status_code == 400
            assert "does not match" in load_resp.json()["detail"]
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_snapshot_load_rejects_schema_version_mismatch(app, manager):
    """Loading a snapshot with an unsupported schema version returns HTTP 400."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            export_resp = await client.get(f"/games/{session.session_id}/snapshot")
            assert export_resp.status_code == 200
            snapshot = export_resp.json()
            snapshot["schema_version"] = 999

            load_resp = await client.put(
                f"/games/{session.session_id}/snapshot",
                json=snapshot,
            )
            assert load_resp.status_code == 400
            assert "Unsupported snapshot schema version" in load_resp.json()["detail"]
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_mcp_does_not_expose_snapshot_tools(mcp):
    """Snapshot HTTP endpoints stay out of MCP discovery."""
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {tool.name for tool in tools}
    assert "export_game_state_snapshot" not in names
    assert "load_game_state_snapshot" not in names


def test_list_actions_catalog(sync_client):
    """GET /actions returns typed actions and curated raw ops."""
    resp = sync_client.get("/actions")
    assert resp.status_code == 200
    body = resp.json()
    assert any(action["type"] == "next_step" for action in body["actions"])
    assert any("SAVE_GAME" in op["example"] for op in body["raw_ops"])


@pytest.mark.asyncio
async def test_get_session_actions_includes_plugin_metadata(app, manager):
    """GET /games/{id}/actions returns plugin-specific metadata."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(f"/games/{session.session_id}/actions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["plugin_name"] == "marvel-champions"
        assert isinstance(body["load_groups"], list)
        assert body["load_groups"]
        assert "named_action_lists" in body["plugin_metadata"]
        assert "player_count_layouts" in body["plugin_metadata"]
        assert any(action["type"] == "next_step" for action in body["actions"])
    finally:
        await manager.delete_session(session.session_id)


def test_search_cards_by_name(sync_client):
    """GET /cards/{provider} returns matching cards for valid filters."""
    resp = sync_client.get("/cards/marvel-champions", params={"name": "spider"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 0
    assert any("spider" in card["name"].lower() for card in body["cards"])


def test_search_cards_rejects_unknown_filter(sync_client):
    """GET /cards/{provider} rejects unsupported filters with HTTP 400."""
    resp = sync_client.get("/cards/marvel-champions", params={"bogus": "x"})
    assert resp.status_code == 400
    assert "Unsupported filter" in resp.json()["detail"]


def test_search_cards_rejects_invalid_filter_value(sync_client):
    """GET /cards/{provider} rejects invalid filter values with HTTP 422."""
    resp = sync_client.get("/cards/marvel-champions", params={"limit": 0})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /games/{id}/actions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_action_next_step(app, manager):
    """POST /games/{id}/actions with next_step returns updated state."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/games/{session.session_id}/actions",
                json={"type": "next_step"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["success"] is True
    finally:
        await manager.delete_session(session.session_id)


@pytest.mark.asyncio
async def test_room_control_http_flows(app, manager):
    """Representative room-control endpoints work through the preserved HTTP surface."""
    session = await manager.create_session("marvel-champions")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            initial_state_resp = await client.get(f"/games/{session.session_id}/state")
            assert initial_state_resp.status_code == 200
            initial_round = initial_state_resp.json()["state"]["game"]["roundNumber"]

            player_count_resp = await client.post(
                f"/games/{session.session_id}/player-count",
                json={"num_players": 2, "layout_id": "standard2Player"},
            )
            assert player_count_resp.status_code == 200
            player_count_body = player_count_resp.json()
            assert player_count_body["session_id"] == session.session_id
            assert "game" in player_count_body["state"]

            alert_resp = await client.post(
                f"/games/{session.session_id}/alert",
                json={"message": "integration alert"},
            )
            assert alert_resp.status_code == 204

            alerts_resp = await client.get(f"/games/{session.session_id}/alerts")
            assert alerts_resp.status_code == 200
            assert any(
                alert.get("text") == "integration alert"
                for alert in alerts_resp.json()["alerts"]
            )

            replay_resp = await client.post(f"/games/{session.session_id}/replay")
            assert replay_resp.status_code == 204

            reset_resp = await client.post(
                f"/games/{session.session_id}/reset", json={}
            )
            assert reset_resp.status_code == 200
            reset_body = reset_resp.json()
            assert reset_body["session_id"] == session.session_id
            assert "game" in reset_body["state"]

            refreshed_state_resp = await client.get(
                f"/games/{session.session_id}/state"
            )
            assert refreshed_state_resp.status_code == 200
            refreshed_round = refreshed_state_resp.json()["state"]["game"][
                "roundNumber"
            ]
            assert refreshed_round <= initial_round
    finally:
        await manager.delete_session(session.session_id)


def test_execute_action_not_found(sync_client):
    """POST /games/{id}/actions with unknown session ID returns 404."""
    resp = sync_client.post(
        "/games/00000000-0000-0000-0000-000000000000/actions",
        json={"type": "next_step"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /games/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_game(app, manager):
    """DELETE /games/{id} deletes the session."""
    session = await manager.create_session("marvel-champions")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.delete(f"/games/{session.session_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_id"] == session.session_id
        assert body["deleted"] is True

        # Session should be gone
        resp2 = await client.get(f"/games/{session.session_id}/state")
        assert resp2.status_code == 404


def test_delete_game_not_found(sync_client):
    """DELETE /games/{id} with unknown ID returns 404."""
    resp = sync_client.delete("/games/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
