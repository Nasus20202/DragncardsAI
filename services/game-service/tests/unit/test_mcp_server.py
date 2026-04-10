"""
Unit tests for game_service.mcp.server

Pure tests — no network, no DragnCards. Covers:
- _format_state_for_llm: None state, dict state
- _action_from_dict: all known types, unknown type raises
- _dispatch_tool: all tools with a mocked SessionManager
- _dispatch_tool: error handling (SessionNotFoundError, ValueError, generic)
- create_mcp_server / list_tools: tool definitions and schemas
- list_resources / read_resource: resource handler behaviour
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.types import (
    ListResourcesRequest,
    ListToolsRequest,
    ReadResourceRequest,
)

from game_service.mcp.server import (
    _action_from_dict,
    _dispatch_tool,
    _format_state_for_llm,
    create_mcp_server,
)
from game_service.session.actions import (
    DrawCardAction,
    MoveCardAction,
    NextStepAction,
    PrevStepAction,
    RawAction,
    SetCardPropertyAction,
)
from game_service.session.manager import SessionError, SessionNotFoundError


# ---------------------------------------------------------------------------
# Helpers for calling MCP request handlers
# ---------------------------------------------------------------------------


async def _call_list_tools(server):
    handler = server.request_handlers[ListToolsRequest]
    result = await handler(ListToolsRequest(method="tools/list"))
    return result.root.tools


async def _call_list_resources(server):
    handler = server.request_handlers[ListResourcesRequest]
    result = await handler(ListResourcesRequest(method="resources/list"))
    return result.root.resources


async def _call_read_resource(server, uri: str):
    handler = server.request_handlers[ReadResourceRequest]
    return await handler(
        ReadResourceRequest(method="resources/read", params={"uri": uri})
    )


# ---------------------------------------------------------------------------
# _format_state_for_llm
# ---------------------------------------------------------------------------


def test_format_state_none():
    result = _format_state_for_llm("sess-1", None)
    assert "sess-1" in result
    assert "no game state" in result.lower()


def test_format_state_dict():
    state = {"game": {"stepId": 5}, "cards": []}
    result = _format_state_for_llm("sess-2", state)
    assert "sess-2" in result
    assert '"stepId"' in result
    assert "5" in result


def test_format_state_contains_json():
    state = {"key": "value"}
    result = _format_state_for_llm("s", state)
    # The JSON should be parseable out of the result
    assert json.dumps(state, indent=2) in result


# ---------------------------------------------------------------------------
# _action_from_dict
# ---------------------------------------------------------------------------


def test_action_from_dict_next_step():
    action = _action_from_dict({"type": "next_step"})
    assert isinstance(action, NextStepAction)


def test_action_from_dict_prev_step():
    action = _action_from_dict({"type": "prev_step"})
    assert isinstance(action, PrevStepAction)


def test_action_from_dict_draw_card():
    action = _action_from_dict({"type": "draw_card", "player_n": "player2", "count": 3})
    assert isinstance(action, DrawCardAction)
    assert action.player_n == "player2"
    assert action.count == 3


def test_action_from_dict_move_card():
    action = _action_from_dict(
        {
            "type": "move_card",
            "card_id": "c1",
            "dest_group_id": "player1Hand",
        }
    )
    assert isinstance(action, MoveCardAction)
    assert action.card_id == "c1"


def test_action_from_dict_set_card_property():
    action = _action_from_dict(
        {
            "type": "set_card_property",
            "card_id": "c1",
            "property_path": "currentSide",
            "value": "B",
        }
    )
    assert isinstance(action, SetCardPropertyAction)
    assert action.value == "B"


def test_action_from_dict_raw():
    action = _action_from_dict({"type": "raw", "action_list": ["NEXT_STEP"]})
    assert isinstance(action, RawAction)
    assert action.action_list == ["NEXT_STEP"]


def test_action_from_dict_unknown_type_raises():
    with pytest.raises(ValueError, match="Unknown action type"):
        _action_from_dict({"type": "teleport_card"})


def test_action_from_dict_missing_type_raises():
    with pytest.raises(ValueError):
        _action_from_dict({})


# ---------------------------------------------------------------------------
# Helpers for building a mock SessionManager
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
    session.execute_action = AsyncMock(return_value={"game": {"stepId": 2}})
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


# ---------------------------------------------------------------------------
# _dispatch_tool: create_game
# ---------------------------------------------------------------------------


async def test_dispatch_create_game_returns_metadata():
    manager = _mock_manager()
    result = await _dispatch_tool("create_game", {}, manager)
    assert len(result) == 1
    text = result[0].text
    assert "sess-abc" in text
    assert "marvel-champions" in text


async def test_dispatch_create_game_custom_plugin():
    manager = _mock_manager()
    await _dispatch_tool("create_game", {"plugin_name": "custom-plugin"}, manager)
    manager.create_session.assert_awaited_once_with("custom-plugin")


async def test_dispatch_create_game_default_plugin():
    manager = _mock_manager()
    await _dispatch_tool("create_game", {}, manager)
    manager.create_session.assert_awaited_once_with("marvel-champions")


# ---------------------------------------------------------------------------
# _dispatch_tool: list_games
# ---------------------------------------------------------------------------


async def test_dispatch_list_games_empty():
    manager = _mock_manager()
    manager.list_sessions.return_value = []
    result = await _dispatch_tool("list_games", {}, manager)
    assert "No active" in result[0].text


async def test_dispatch_list_games_with_sessions():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    result = await _dispatch_tool("list_games", {}, manager)
    text = result[0].text
    assert "sess-abc" in text


# ---------------------------------------------------------------------------
# _dispatch_tool: get_game_state
# ---------------------------------------------------------------------------


async def test_dispatch_get_game_state():
    session = _mock_session(state={"game": {"stepId": 7}})
    manager = _mock_manager(sessions=[session])
    result = await _dispatch_tool("get_game_state", {"session_id": "sess-abc"}, manager)
    text = result[0].text
    assert "sess-abc" in text
    assert "7" in text


async def test_dispatch_get_game_state_not_found():
    manager = _mock_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("not found"))
    result = await _dispatch_tool("get_game_state", {"session_id": "bad"}, manager)
    assert "Error (not found)" in result[0].text


# ---------------------------------------------------------------------------
# _dispatch_tool: execute_action
# ---------------------------------------------------------------------------


async def test_dispatch_execute_action_next_step():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    result = await _dispatch_tool(
        "execute_action",
        {"session_id": "sess-abc", "action": {"type": "next_step"}},
        manager,
    )
    text = result[0].text
    assert "Action executed" in text
    session.execute_action.assert_awaited_once()


async def test_dispatch_execute_action_invalid_type():
    manager = _mock_manager()
    result = await _dispatch_tool(
        "execute_action",
        {"session_id": "sess-abc", "action": {"type": "bad_type"}},
        manager,
    )
    assert "Error (invalid input)" in result[0].text


async def test_dispatch_execute_action_session_error():
    session = _mock_session()
    session.execute_action = AsyncMock(side_effect=SessionError("rejected"))
    manager = _mock_manager(sessions=[session])
    result = await _dispatch_tool(
        "execute_action",
        {"session_id": "sess-abc", "action": {"type": "next_step"}},
        manager,
    )
    assert "Error (session)" in result[0].text


# ---------------------------------------------------------------------------
# _dispatch_tool: delete_game
# ---------------------------------------------------------------------------


async def test_dispatch_delete_game():
    manager = _mock_manager()
    result = await _dispatch_tool("delete_game", {"session_id": "sess-abc"}, manager)
    assert "deleted" in result[0].text.lower()
    manager.delete_session.assert_awaited_once_with("sess-abc")


async def test_dispatch_delete_game_not_found():
    manager = _mock_manager()
    manager.delete_session = AsyncMock(side_effect=SessionNotFoundError("nope"))
    result = await _dispatch_tool("delete_game", {"session_id": "bad"}, manager)
    assert "Error (not found)" in result[0].text


# ---------------------------------------------------------------------------
# _dispatch_tool: unknown tool
# ---------------------------------------------------------------------------


async def test_dispatch_unknown_tool():
    manager = _mock_manager()
    result = await _dispatch_tool("fly_to_moon", {}, manager)
    assert "Error" in result[0].text


# ---------------------------------------------------------------------------
# _dispatch_tool: return-type contract
# ---------------------------------------------------------------------------


async def test_dispatch_returns_list_of_text_content():
    """_dispatch_tool always returns list[TextContent] with type='text'."""
    manager = _mock_manager()
    result = await _dispatch_tool("list_games", {}, manager)
    assert isinstance(result, list)
    assert len(result) >= 1
    assert result[0].type == "text"
    assert isinstance(result[0].text, str)


async def test_dispatch_error_path_returns_list_of_text_content():
    """Error paths also return list[TextContent]."""
    manager = _mock_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("gone"))
    result = await _dispatch_tool("get_game_state", {"session_id": "x"}, manager)
    assert isinstance(result, list)
    assert result[0].type == "text"


# ---------------------------------------------------------------------------
# _dispatch_tool: additional error paths
# ---------------------------------------------------------------------------


async def test_dispatch_create_game_session_error():
    """create_game propagates SessionError from manager.create_session."""
    manager = _mock_manager()
    manager.create_session = AsyncMock(side_effect=SessionError("plugin not found"))
    result = await _dispatch_tool("create_game", {"plugin_name": "bad-plugin"}, manager)
    assert "Error (session)" in result[0].text
    assert "plugin not found" in result[0].text


async def test_dispatch_execute_action_session_not_found():
    """execute_action surfaces SessionNotFoundError from get_session."""
    manager = _mock_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("no such session"))
    result = await _dispatch_tool(
        "execute_action",
        {"session_id": "missing", "action": {"type": "next_step"}},
        manager,
    )
    assert "Error (not found)" in result[0].text


async def test_dispatch_unexpected_exception():
    """Bare Exception is caught and returned as Error (unexpected)."""
    manager = _mock_manager()
    manager.list_sessions = MagicMock(side_effect=RuntimeError("boom"))
    result = await _dispatch_tool("list_games", {}, manager)
    assert "Error (unexpected)" in result[0].text
    assert "boom" in result[0].text


# ---------------------------------------------------------------------------
# create_mcp_server / list_tools
# ---------------------------------------------------------------------------


EXPECTED_TOOL_NAMES = {
    "create_game",
    "list_games",
    "get_game_state",
    "execute_action",
    "delete_game",
}


async def test_list_tools_returns_five_tools():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    tools = await _call_list_tools(server)
    assert len(tools) == 5


async def test_list_tools_names():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    tools = await _call_list_tools(server)
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES


async def test_list_tools_get_game_state_requires_session_id():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    tools = await _call_list_tools(server)
    tool = next(t for t in tools if t.name == "get_game_state")
    assert "session_id" in tool.inputSchema["required"]


async def test_list_tools_execute_action_required_fields():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    tools = await _call_list_tools(server)
    tool = next(t for t in tools if t.name == "execute_action")
    assert "session_id" in tool.inputSchema["required"]
    assert "action" in tool.inputSchema["required"]


async def test_list_tools_create_game_has_no_required_fields():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    tools = await _call_list_tools(server)
    tool = next(t for t in tools if t.name == "create_game")
    assert tool.inputSchema.get("required", []) == []


async def test_list_tools_all_have_descriptions():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    tools = await _call_list_tools(server)
    for tool in tools:
        assert tool.description, f"Tool {tool.name!r} has no description"


# ---------------------------------------------------------------------------
# list_resources
# ---------------------------------------------------------------------------


async def test_list_resources_empty_when_no_sessions():
    manager = _mock_manager()
    manager.list_sessions.return_value = []
    server = create_mcp_server(manager)
    resources = await _call_list_resources(server)
    assert resources == []


async def test_list_resources_one_entry_per_session():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    server = create_mcp_server(manager)
    resources = await _call_list_resources(server)
    assert len(resources) == 1


async def test_list_resources_uri_format():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    server = create_mcp_server(manager)
    resources = await _call_list_resources(server)
    assert str(resources[0].uri) == "game://sess-abc/state"


async def test_list_resources_mime_type():
    session = _mock_session()
    manager = _mock_manager(sessions=[session])
    server = create_mcp_server(manager)
    resources = await _call_list_resources(server)
    assert resources[0].mimeType == "application/json"


# ---------------------------------------------------------------------------
# read_resource
# ---------------------------------------------------------------------------


async def test_read_resource_returns_state_json():
    session = _mock_session(state={"game": {"stepId": 3}})
    manager = _mock_manager(sessions=[session])
    server = create_mcp_server(manager)
    result = await _call_read_resource(server, "game://sess-abc/state")
    content = result.root.contents[0]
    assert content.mimeType == "application/json"
    parsed = json.loads(content.text)
    assert parsed["game"]["stepId"] == 3


async def test_read_resource_none_state_returns_null():
    session = _mock_session()
    session.get_state = AsyncMock(return_value=None)
    manager = _mock_manager(sessions=[session])
    server = create_mcp_server(manager)
    result = await _call_read_resource(server, "game://sess-abc/state")
    assert result.root.contents[0].text == "null"


async def test_read_resource_invalid_uri_raises():
    manager = _mock_manager()
    server = create_mcp_server(manager)
    with pytest.raises(Exception, match="Unknown resource URI"):
        await _call_read_resource(server, "http://bad/uri")


async def test_read_resource_session_not_found_raises():
    manager = _mock_manager()
    manager.get_session = AsyncMock(side_effect=SessionNotFoundError("gone"))
    server = create_mcp_server(manager)
    with pytest.raises(SessionNotFoundError):
        await _call_read_resource(server, "game://missing-id/state")
