"""The session-mode API: the default, the two accepted values, and the refusals."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .app_test_support import build_test_app


@pytest.mark.asyncio
async def test_session_mode_defaults_to_chat(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            created = client.post("/sessions", json={"name": "plain"})
            assert created.status_code == 201
            assert created.json()["session"]["session_mode"] == "chat"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_can_be_created_orchestrated(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/sessions", json={"name": "table", "session_mode": "orchestrated"}
            )
            assert created.status_code == 201
            assert created.json()["session"]["session_mode"] == "orchestrated"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_unknown_session_mode_is_rejected(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            created = client.post(
                "/sessions", json={"name": "odd", "session_mode": "supervisor"}
            )
            assert created.status_code == 422

            session_id = client.post("/sessions", json={"name": "plain"}).json()[
                "session"
            ]["id"]
            patched = client.patch(
                f"/sessions/{session_id}", json={"session_mode": "supervisor"}
            )
            assert patched.status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mode_can_be_changed_before_the_first_prompt(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "plain"}).json()[
                "session"
            ]["id"]

            patched = client.patch(
                f"/sessions/{session_id}", json={"session_mode": "orchestrated"}
            )

            assert patched.status_code == 200
            assert patched.json()["session"]["session_mode"] == "orchestrated"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_mode_change_is_refused_with_conflict_after_a_prompt(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "plain"}).json()[
                "session"
            ]["id"]
            queued = client.post(
                f"/sessions/{session_id}/prompts", json={"prompt": "hello"}
            )
            assert queued.status_code in (200, 201, 202)

            patched = client.patch(
                f"/sessions/{session_id}", json={"session_mode": "orchestrated"}
            )

            assert patched.status_code == 409
            reread = client.get(f"/sessions/{session_id}").json()["session"]
            assert reread["session_mode"] == "chat"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_an_unrelated_patch_still_works_after_a_prompt(tmp_path: Path):
    """Echoing the unchanged mode back must not turn a rename into a 409."""
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            session_id = client.post("/sessions", json={"name": "plain"}).json()[
                "session"
            ]["id"]
            client.post(f"/sessions/{session_id}/prompts", json={"prompt": "hello"})

            patched = client.patch(
                f"/sessions/{session_id}",
                json={"name": "renamed", "session_mode": "chat"},
            )

            assert patched.status_code == 200
            assert patched.json()["session"]["name"] == "renamed"
    finally:
        await engine.dispose()
