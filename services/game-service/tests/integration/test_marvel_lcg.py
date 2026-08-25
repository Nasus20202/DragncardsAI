"""Opt-in integration coverage for the real Marvel LCG engine.

Run this scaffold only with the Marvel LCG profile active::

    MARVEL_LCG_INTEGRATION=1 \
    MARVEL_LCG_HTTP_URL=http://localhost:4006 \
    MARVEL_LCG_PASSWORD=... \
    uv run pytest tests/integration/test_marvel_lcg.py -v

The test deliberately uses the HTTP API, waits only within bounded deadlines,
chooses an option id returned by the engine, and tears the session down even
when the option flow fails.
"""

from __future__ import annotations

import asyncio
import os

import httpx
import pytest

from game_service.api.app import create_app
from game_service.coordination.history_emitter import NullHistoryEmitter
from game_service.coordination.session_store import ValkeySessionStore
from game_service.logic.platform import MARVEL_LCG_PLATFORM
from game_service.logic.session_manager import SessionManager
from game_service.marvel_lcg.platform import MarvelLcgPlatform

pytestmark = [pytest.mark.live, pytest.mark.marvel_lcg]


async def _wait_for_engine_option(
    client: httpx.AsyncClient,
    session_id: str,
    *,
    timeout: float,
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        response = await client.get(
            f"/games/{session_id}/options",
            params={"player_n": "player1"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["options"]:
            return payload
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            pytest.fail(
                "Marvel LCG did not expose an engine option before the deadline"
            )
        await asyncio.sleep(min(0.25, remaining))


async def test_marvel_lcg_real_engine_option_round_trip():
    http_url = os.environ["MARVEL_LCG_HTTP_URL"]
    password = os.environ["MARVEL_LCG_PASSWORD"]
    platform = MarvelLcgPlatform(
        http_url,
        password,
        ws_url=os.environ.get("MARVEL_LCG_WS_URL"),
        scenario_path=os.environ.get("MARVEL_LCG_SCENARIO_PATH"),
        hero_paths=(
            (os.environ["MARVEL_LCG_HERO_PATH"],)
            if os.environ.get("MARVEL_LCG_HERO_PATH")
            else ()
        ),
        ready_timeout=10.0,
        move_timeout=10.0,
    )
    manager = SessionManager(
        platform_registry={MARVEL_LCG_PLATFORM: platform},
        session_store=ValkeySessionStore(
            os.environ.get("VALKEY_URL", "redis://localhost:6380/0")
        ),
        history_emitter=NullHistoryEmitter(),
    )
    app = create_app(session_manager=manager)
    session_id: str | None = None

    async def exercise() -> None:
        nonlocal session_id
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            timeout=15.0,
        ) as client:
            catalog = await client.get(
                "/games/setup-catalog", params={"platform": "marvel-lcg"}
            )
            assert catalog.status_code == 200, catalog.text
            catalog_body = catalog.json()
            scenario_id = catalog_body["scenarios"][0]["id"]
            hero_decks = catalog_body["hero_decks"]
            assert len(hero_decks) >= 2

            created = await client.post(
                "/games",
                json={
                    "platform": "marvel-lcg",
                    "setup": {
                        "platform": "marvel-lcg",
                        "scenario_id": scenario_id,
                        "hero_decks": [
                            {
                                "seat": "player1",
                                "hero_deck_id": hero_decks[0]["id"],
                            },
                            {
                                "seat": "player2",
                                "hero_deck_id": hero_decks[1]["id"],
                            },
                        ],
                    },
                },
            )
            assert created.status_code == 201, created.text
            session_id = created.json()["session"]["session_id"]

            options = await _wait_for_engine_option(client, session_id, timeout=20.0)
            option = options["options"][0]
            assert "id" in option
            chosen_id = option["id"]

            chosen = await client.post(
                f"/games/{session_id}/options/choose",
                json={
                    "player_n": "player1",
                    "option_id": chosen_id,
                    "prompt_id": options["prompt_id"],
                    "prompt_version": options["prompt_version"],
                },
            )
            assert chosen.status_code == 200, chosen.text
            assert chosen.json()["option_id"] == chosen_id

    try:
        await asyncio.wait_for(exercise(), timeout=90.0)
    finally:
        if session_id is not None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
                timeout=15.0,
            ) as client:
                await client.delete(f"/games/{session_id}")
            if session_id in manager._sessions:
                await manager.delete_session(session_id)
