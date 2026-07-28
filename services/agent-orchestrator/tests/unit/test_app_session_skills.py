"""
Session skill enablement, including tolerance for stale skill state.

A `session_enabled_skills` row is a soft toggle, so a session that once had a
skill keeps a row with `enabled=false` after it is turned off. These tests pin
the behaviour that made a session unplayable: the dashboard saves a session
config by replaying the desired skill set, so any request that rejected an
already-correct state aborted the whole save.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent_orchestrator.runtime.skills import (
    SkillRegistry,
    enabled_skill_assignments,
)
from agent_orchestrator.runtime.system_prompts import build_system_prompt

from .app_test_support import build_test_app


def _create_session(client: TestClient) -> str:
    return client.post("/sessions", json={"name": "skills"}).json()["session"]["id"]


def test_on_disk_skill_is_enablable_without_prior_registration(app):
    # Enabling needs a global registry row. Rows used to appear only as a side
    # effect of the enable-by-POST route, so a skill present in the skill roots
    # was not necessarily enablable.
    with TestClient(app) as client:
        session_id = _create_session(client)

        response = client.patch(
            f"/sessions/{session_id}/skills/demo-skill", json={"enabled": True}
        )

        assert response.status_code == 200
        assert response.json()["skill"] == {"name": "demo-skill", "enabled": True}
        listed = client.get(f"/sessions/{session_id}/skills").json()["skills"]
        assert [skill["skill_name"] for skill in listed] == ["demo-skill"]


def test_enabling_a_skill_that_is_not_on_disk_is_rejected(app):
    with TestClient(app) as client:
        session_id = _create_session(client)

        response = client.patch(
            f"/sessions/{session_id}/skills/no-such-skill", json={"enabled": True}
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Unknown skill"


def test_a_disabled_skill_is_absent_from_the_session_payload(app):
    # The session payload drives the dashboard's skill toggles. Reporting a
    # disabled skill as assigned made the toggle spring back on, and the next
    # save then tried to disable it again.
    with TestClient(app) as client:
        session_id = _create_session(client)
        client.post(f"/sessions/{session_id}/skills", json={"skill_name": "demo-skill"})

        assert client.get(f"/sessions/{session_id}").json()["session"]["skills"]

        client.delete(f"/sessions/{session_id}/skills/demo-skill")

        assert client.get(f"/sessions/{session_id}").json()["session"]["skills"] == []
        assert client.get("/sessions").json()["sessions"][0]["skills"] == []


def test_disabling_a_skill_is_idempotent(app):
    with TestClient(app) as client:
        session_id = _create_session(client)
        client.post(f"/sessions/{session_id}/skills", json={"skill_name": "demo-skill"})

        first = client.delete(f"/sessions/{session_id}/skills/demo-skill")
        second = client.delete(f"/sessions/{session_id}/skills/demo-skill")
        patched = client.patch(
            f"/sessions/{session_id}/skills/demo-skill", json={"enabled": False}
        )

        assert first.status_code == 204
        assert second.status_code == 204
        assert patched.status_code == 200
        assert patched.json()["skill"] == {"name": "demo-skill", "enabled": False}


def test_disabling_a_never_enabled_skill_is_a_no_op(app):
    with TestClient(app) as client:
        session_id = _create_session(client)

        assert (
            client.delete(f"/sessions/{session_id}/skills/demo-skill").status_code
            == 204
        )
        # A skill that is not even on disk cannot be enabled, so the session is
        # already in the requested state.
        assert (
            client.delete(f"/sessions/{session_id}/skills/gone-skill").status_code
            == 204
        )


def test_disabling_a_skill_for_an_unknown_session_is_rejected(app):
    with TestClient(app) as client:
        assert client.delete("/sessions/missing/skills/demo-skill").status_code == 404
        assert (
            client.patch(
                "/sessions/missing/skills/demo-skill", json={"enabled": True}
            ).status_code
            == 404
        )


def test_a_disabled_skill_can_be_enabled_again(app):
    with TestClient(app) as client:
        session_id = _create_session(client)
        client.post(f"/sessions/{session_id}/skills", json={"skill_name": "demo-skill"})
        client.delete(f"/sessions/{session_id}/skills/demo-skill")

        response = client.post(
            f"/sessions/{session_id}/skills", json={"skill_name": "demo-skill"}
        )

        assert response.status_code == 201
        listed = client.get(f"/sessions/{session_id}/skills").json()["skills"]
        assert [skill["skill_name"] for skill in listed] == ["demo-skill"]


@pytest.mark.asyncio
async def test_startup_syncs_on_disk_skills_into_the_registry(tmp_path: Path):
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app):
            registries = await app.state.repository.list_skill_registries()

        assert [item.name for item in registries] == ["demo-skill"]
        assert registries[0].skill_path == str(tmp_path / "skills" / "demo-skill")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_a_skill_added_after_startup_is_still_enablable(tmp_path: Path):
    # The skill roots are read from disk, so they can gain a skill while the
    # service is running. Enablement registers on demand rather than relying
    # only on the sync at startup.
    app, engine = await build_test_app(tmp_path)
    try:
        with TestClient(app) as client:
            late = tmp_path / "skills" / "late-skill"
            late.mkdir()
            (late / "SKILL.md").write_text("late skill", encoding="utf-8")

            session_id = _create_session(client)
            response = client.patch(
                f"/sessions/{session_id}/skills/late-skill", json={"enabled": True}
            )

            assert response.status_code == 200
            listed = client.get(f"/sessions/{session_id}/skills").json()["skills"]
            assert [skill["skill_name"] for skill in listed] == ["late-skill"]
    finally:
        await engine.dispose()


def test_enabled_skill_assignments_drops_disabled_rows():
    assignments = [
        SimpleNamespace(skill_name="on", enabled=True),
        SimpleNamespace(skill_name="off", enabled=False),
    ]

    assert [item.skill_name for item in enabled_skill_assignments(assignments)] == [
        "on"
    ]
    assert enabled_skill_assignments([]) == []
    assert enabled_skill_assignments(None) == []


def test_a_disabled_skill_is_not_advertised_in_the_system_prompt(tmp_path: Path):
    # Turning a skill off has to stop the agent seeing it, or "disabled" only
    # means "hidden from the dashboard".
    skill_root = tmp_path / "skills"
    for name in ("on-skill", "off-skill"):
        skill_dir = skill_root / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"{name} body", encoding="utf-8")
    assignments = [
        SimpleNamespace(skill_name="on-skill", enabled=True),
        SimpleNamespace(skill_name="off-skill", enabled=False),
    ]

    prompt = build_system_prompt(
        SkillRegistry((skill_root,)), enabled_skill_assignments(assignments)
    )

    assert "on-skill" in prompt
    assert "off-skill" not in prompt
