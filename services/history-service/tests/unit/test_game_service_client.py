from __future__ import annotations

import httpx
import pytest

from history_service.integrations.game_service import GameServiceClient


def _client_with_capture(captured: list[httpx.Request]) -> GameServiceClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    client = GameServiceClient("http://game:9")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


@pytest.mark.asyncio
async def test_path_params_are_url_encoded():
    captured: list[httpx.Request] = []
    client = _client_with_capture(captured)
    # An id with characters that would otherwise break out of a path segment is
    # percent-encoded, so it cannot inject extra segments against the upstream.
    await client.get_snapshot("a/b/../c")
    assert len(captured) == 1
    url = captured[0].url
    # The slashes stay inside one encoded segment; no extra path segments appear.
    assert url.raw_path == b"/games/a%2Fb%2F..%2Fc/snapshot"
    await client.aclose()


@pytest.mark.asyncio
async def test_replay_encodes_game_id_and_allowed_suffix():
    captured: list[httpx.Request] = []
    client = _client_with_capture(captured)
    await client.replay_action(
        "branch-1", {"action_path": "actions/move_card", "action_args": {"x": 1}}
    )
    assert captured[0].url.raw_path == b"/games/branch-1/actions/move_card"
    await client.aclose()


@pytest.mark.asyncio
async def test_replay_accepts_generic_actions_path():
    captured: list[httpx.Request] = []
    client = _client_with_capture(captured)
    await client.replay_action("g1", {"action_path": "actions", "action_args": {}})
    assert captured[0].url.raw_path == b"/games/g1/actions"
    await client.aclose()


@pytest.mark.parametrize(
    "bad_path",
    [
        "actions/../delete",
        "../../games/victim/delete",
        "actions/a/b",
        "actions move",
        "actions?x=1",
        "http://evil/steal",
    ],
)
@pytest.mark.asyncio
async def test_replay_rejects_disallowed_action_path(bad_path):
    captured: list[httpx.Request] = []
    client = _client_with_capture(captured)
    with pytest.raises(ValueError, match="disallowed action_path"):
        await client.replay_action("g1", {"action_path": bad_path, "action_args": {}})
    # Nothing was forwarded to the upstream.
    assert captured == []
    await client.aclose()


@pytest.mark.asyncio
async def test_replay_missing_action_path_raises():
    client = _client_with_capture([])
    with pytest.raises(ValueError, match="missing 'action_path'"):
        await client.replay_action("g1", {"action_args": {}})
    await client.aclose()
