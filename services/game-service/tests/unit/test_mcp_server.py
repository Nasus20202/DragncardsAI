"""
Unit tests for game_service.mcp.server

The MCP server is now auto-generated from the FastAPI app via
FastMCP.from_fastapi(). Tests here cover:

- create_mcp_server produces the expected tool names and schemas
- All expected tools are present (one per HTTP endpoint, minus /health)
- Resources (state, alerts, gui-update) read from the in-process SessionManager
- Resource error propagation (SessionNotFoundError)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Client

from game_service.api.app import create_app
from game_service.mcp.server import create_mcp_server
from game_service.session.manager import SessionNotFoundError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _mock_session(state=None):
    session = MagicMock()
    session.to_metadata.return_value = {
        "session_id": "sess-abc",
        "plugin_name": "marvel-champions",
        "plugin_id": 1,
        "room_slug": "abc123",
        "created_at": "2024-01-01T00:00:00+00:00",
    }
    session.get_state = AsyncMock(return_value=state or {"game": {}})
    session.get_alerts = MagicMock(return_value=[{"level": "info", "text": "hi"}])
    session.get_gui_updates = MagicMock(
        return_value={"player1": {"player_n": "player1", "prompt": "choose"}}
    )
    return session


def _mock_manager(sessions=None):
    manager = MagicMock()
    _sessions = sessions or []
    manager.list_sessions.return_value = [s.to_metadata() for s in _sessions]
    if _sessions:
        manager.create_session = AsyncMock(return_value=_sessions[0])
        manager.get_session = AsyncMock(return_value=_sessions[0])
    else:
        manager.create_session = AsyncMock(return_value=_mock_session())
        manager.get_session = AsyncMock(return_value=_mock_session())
    manager.delete_session = AsyncMock()
    return manager


def _make_mcp(manager=None):
    if manager is None:
        manager = _mock_manager()
    app = create_app(session_manager=manager)
    return create_mcp_server(session_manager=manager, fastapi_app=app)


# ---------------------------------------------------------------------------
# Tool names and schemas
# ---------------------------------------------------------------------------

EXPECTED_TOOL_NAMES = {
    "create_game",
    "attach_game",
    "list_games",
    "get_game_state",
    "execute_action",
    "delete_game",
    "reset_game",
    "set_seat",
    "set_spectator",
    "send_alert",
    "save_replay",
    "set_player_count",
    "list_actions",
    "search_cards",
    "get_session_actions",
}


async def test_tool_count():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    assert len(tools) == len(EXPECTED_TOOL_NAMES)


async def test_tool_names():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES


async def test_health_excluded():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    names = {t.name for t in tools}
    assert "health" not in names


async def test_all_tools_have_descriptions():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    for tool in tools:
        assert tool.description, f"Tool {tool.name!r} has no description"


async def test_execute_action_requires_session_id_and_action():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "execute_action")
    required = tool.inputSchema.get("required", [])
    assert "session_id" in required
    assert "action" in required


async def test_get_game_state_requires_session_id():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "get_game_state")
    assert "session_id" in tool.inputSchema.get("required", [])


async def test_create_game_has_no_required_fields():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "create_game")
    assert tool.inputSchema.get("required", []) == []


async def test_set_player_count_requires_num_players():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        tools = await client.list_tools()
    tool = next(t for t in tools if t.name == "set_player_count")
    assert "num_players" in tool.inputSchema.get("required", [])


# ---------------------------------------------------------------------------
# Resources: list (templates)
# ---------------------------------------------------------------------------

EXPECTED_RESOURCE_TEMPLATES = {
    "game://{session_id}/state",
    "game://{session_id}/alerts",
    "game://{session_id}/gui-update",
}


async def test_list_resources_empty_when_no_sessions():
    """Static resources list is empty — resources are exposed as templates."""
    manager = _mock_manager()
    manager.list_sessions.return_value = []
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        resources = await client.list_resources()
    assert resources == []


async def test_list_resource_templates_count():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    assert len(templates) == 3


async def test_list_resource_templates_uris():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    uris = {t.uriTemplate for t in templates}
    assert uris == EXPECTED_RESOURCE_TEMPLATES


async def test_list_resource_templates_have_descriptions():
    mcp = _make_mcp()
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
    for t in templates:
        assert t.description, f"Template {t.uriTemplate!r} has no description"


# ---------------------------------------------------------------------------
# Resources: read — state
# ---------------------------------------------------------------------------


async def test_read_resource_state_returns_json():
    session = _mock_session(state={"game": {"stepId": 3}})
    manager = _mock_manager(sessions=[session])
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        result = await client.read_resource("game://sess-abc/state")
    parsed = json.loads(result[0].text)
    assert parsed["game"]["stepId"] == 3


async def test_read_resource_state_none_returns_null():
    session = _mock_session()
    session.get_state = AsyncMock(return_value=None)
    manager = _mock_manager(sessions=[session])
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        result = await client.read_resource("game://sess-abc/state")
    assert result[0].text == "null"


# ---------------------------------------------------------------------------
# Resources: read — alerts
# ---------------------------------------------------------------------------


async def test_read_resource_alerts():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        result = await client.read_resource("game://sess-abc/alerts")
    parsed = json.loads(result[0].text)
    assert isinstance(parsed, list)
    assert parsed[0]["text"] == "hi"


async def test_read_resource_alerts_empty():
    session = _mock_session()
    session.get_alerts = MagicMock(return_value=[])
    manager = _mock_manager(sessions=[session])
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        result = await client.read_resource("game://sess-abc/alerts")
    assert json.loads(result[0].text) == []


# ---------------------------------------------------------------------------
# Resources: read — gui-update
# ---------------------------------------------------------------------------


async def test_read_resource_gui_update():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        result = await client.read_resource("game://sess-abc/gui-update")
    parsed = json.loads(result[0].text)
    assert "player1" in parsed
    assert parsed["player1"]["prompt"] == "choose"


async def test_read_resource_gui_update_empty():
    session = _mock_session()
    session.get_gui_updates = MagicMock(return_value={})
    manager = _mock_manager(sessions=[session])
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        result = await client.read_resource("game://sess-abc/gui-update")
    assert json.loads(result[0].text) == {}


# ---------------------------------------------------------------------------
# Resources: error propagation
# ---------------------------------------------------------------------------


async def test_read_resource_state_session_not_found():
    manager = _mock_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("gone"))
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.read_resource("game://missing/state")


async def test_read_resource_alerts_session_not_found():
    manager = _mock_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("gone"))
    mcp = _make_mcp(manager)
    async with Client(mcp) as client:
        with pytest.raises(Exception):
            await client.read_resource("game://missing/alerts")
