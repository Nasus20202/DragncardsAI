"""
End-to-end tests: HTTP API + MCP tools + concurrent access.

Requires a running DragnCards instance with the Marvel Champions plugin.

Run with:
    pytest tests/integration/test_e2e.py -v

Note: All tests that call endpoints involving WebSocket operations use
httpx.AsyncClient with ASGI transport so the event loop stays free for
background WebSocket receiver tasks.
"""

import asyncio
import json
import os

import httpx
import pytest
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


# ---------------------------------------------------------------------------
# 7.1  End-to-end via HTTP API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_http_game_lifecycle(app, manager):
    """
    Full lifecycle via HTTP:
      1. Create a game session
      2. Query initial state (has 'game' key)
      3. Execute next_step action (state updates)
      4. Delete session
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        # 1. Create
        create_resp = await client.post(
            "/games", json={"plugin_name": "marvel-champions"}
        )
        assert create_resp.status_code == 201
        session_id = create_resp.json()["session"]["session_id"]

        try:
            # 2. Query initial state
            state_resp = await client.get(f"/games/{session_id}/state")
            assert state_resp.status_code == 200
            state_before = state_resp.json()["state"]
            assert state_before is not None
            assert "game" in state_before

            # 3. Execute next_step
            action_resp = await client.post(
                f"/games/{session_id}/actions",
                json={"type": "next_step"},
            )
            assert action_resp.status_code == 200
            assert action_resp.json()["success"] is True

            state_after_resp = await client.get(f"/games/{session_id}/state")
            assert state_after_resp.status_code == 200
            state_after = state_after_resp.json()["state"]
            assert state_after is not None
            assert "game" in state_after

        finally:
            # 4. Delete
            del_resp = await client.delete(f"/games/{session_id}")
            assert del_resp.status_code == 200

        # Session should be gone
        gone = await client.get(f"/games/{session_id}/state")
        assert gone.status_code == 404


# ---------------------------------------------------------------------------
# 7.2  End-to-end via MCP tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_mcp_game_lifecycle(app, mcp):
    """
    Full lifecycle via MCP tools:
      1. create_game
      2. query state through HTTP
      3. execute_action (next_step)
      4. delete_game
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        async with Client(mcp) as client:
            # 1. Create
            result = await client.call_tool(
                "create_game", {"plugin_name": "marvel-champions"}
            )
            text = result.content[0].text
            assert "session_id" in text
            data = json.loads(text)
            session_id = data["session"]["session_id"]

            try:
                # 2. Get state through HTTP
                state_resp = await http_client.get(f"/games/{session_id}/state")
                assert state_resp.status_code == 200
                state_data = state_resp.json()
                assert state_data["session_id"] == session_id
                assert "game" in state_data["state"]

                # 3. Execute next_step
                action_result = await client.call_tool(
                    "execute_action",
                    {"session_id": session_id, "action": {"type": "next_step"}},
                )
                action_data = json.loads(action_result.content[0].text)
                assert action_data["session_id"] == session_id
                assert action_data["success"] is True

                state_after_resp = await http_client.get(f"/games/{session_id}/state")
                assert state_after_resp.status_code == 200
                assert "game" in state_after_resp.json()["state"]

            finally:
                # 4. Delete
                del_result = await client.call_tool(
                    "delete_game", {"session_id": session_id}
                )
                del_data = json.loads(del_result.content[0].text)
                assert del_data["session_id"] == session_id


# ---------------------------------------------------------------------------
# 7.3  Concurrent HTTP + MCP access to the same session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_e2e_concurrent_http_and_mcp(app, mcp, manager):
    """
    Both HTTP and MCP interfaces can interact with the same session state
    and return consistent results.
    """
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        async with Client(mcp) as mcp_client:
            # Create session via HTTP
            create_resp = await http_client.post(
                "/games", json={"plugin_name": "marvel-champions"}
            )
            assert create_resp.status_code == 201
            session_id = create_resp.json()["session"]["session_id"]

            try:
                # Concurrently query state via HTTP and run an MCP action
                async def http_query():
                    resp = await http_client.get(f"/games/{session_id}/state")
                    return resp.json()["state"]

                async def mcp_query():
                    result = await mcp_client.call_tool(
                        "execute_action",
                        {"session_id": session_id, "action": {"type": "next_step"}},
                    )
                    resp = await http_client.get(f"/games/{session_id}/state")
                    return resp.json()["state"]

                http_state, mcp_state = await asyncio.gather(http_query(), mcp_query())

                # Both should return valid state
                assert http_state is not None
                assert "game" in http_state
                assert mcp_state is not None
                assert "game" in mcp_state

                # HTTP should still see state after the MCP action
                after_resp = await http_client.get(f"/games/{session_id}/state")
                assert after_resp.status_code == 200
                after_state = after_resp.json()["state"]
                assert "game" in after_state

            finally:
                await manager.delete_session(session_id)
