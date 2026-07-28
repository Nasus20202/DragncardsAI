from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_orchestrator.runtime.skills import (
    JOB_INLINE_SKILLS_KEY,
    MAX_INLINE_SKILLS,
    SkillRegistry,
    render_prompt_with_inline_skills,
)


def _registry(tmp_path: Path, *names: str) -> SkillRegistry:
    for name in names:
        skill_dir = tmp_path / name
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(f"{name} body", encoding="utf-8")
    return SkillRegistry((tmp_path,))


def test_render_puts_skill_content_ahead_of_the_prompt(tmp_path: Path):
    registry = _registry(tmp_path, "alpha-skill")

    content, loaded = render_prompt_with_inline_skills(
        registry, ["alpha-skill"], "play the villain phase"
    )

    assert loaded == ["alpha-skill"]
    assert "## Skill: alpha-skill" in content
    assert "alpha-skill body" in content
    assert content.endswith("play the villain phase")
    assert content.index("alpha-skill body") < content.index("play the villain phase")


def test_render_includes_the_reference_inventory(tmp_path: Path):
    registry = _registry(tmp_path, "alpha-skill")
    references = tmp_path / "alpha-skill" / "resources"
    references.mkdir()
    (references / "timing.md").write_text("timing", encoding="utf-8")

    content, _ = render_prompt_with_inline_skills(registry, ["alpha-skill"], "go")

    assert "resources/timing.md" in content


def test_render_collapses_repeats_and_keeps_order(tmp_path: Path):
    registry = _registry(tmp_path, "alpha-skill", "beta-skill")

    content, loaded = render_prompt_with_inline_skills(
        registry, ["beta-skill", "alpha-skill", "beta-skill"], "go"
    )

    assert loaded == ["beta-skill", "alpha-skill"]
    assert content.index("beta-skill body") < content.index("alpha-skill body")


def test_render_skips_a_skill_that_no_longer_resolves(tmp_path: Path):
    registry = _registry(tmp_path, "alpha-skill")

    content, loaded = render_prompt_with_inline_skills(registry, ["gone-skill"], "go")

    assert loaded == []
    assert content == "go"


def test_render_without_skills_returns_the_prompt_unchanged(tmp_path: Path):
    registry = _registry(tmp_path, "alpha-skill")

    assert render_prompt_with_inline_skills(registry, [], "go") == ("go", [])


def _session_id(client: TestClient) -> str:
    session_id = client.post("/sessions", json={"name": "demo"}).json()["session"]["id"]
    client.put(
        f"/sessions/{session_id}/model-config",
        json={"provider_id": "openai", "model_name": "gpt-4o-mini"},
    )
    return session_id


def test_submit_prompt_records_the_loaded_skills(app):
    with TestClient(app) as client:
        session_id = _session_id(client)
        response = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "@demo-skill go", "inline_skills": ["demo-skill"]},
        )

    assert response.status_code == 202
    assert response.json()["job"]["metadata"] == {JOB_INLINE_SKILLS_KEY: ["demo-skill"]}


def test_submit_prompt_collapses_repeated_skill_names(app):
    with TestClient(app) as client:
        session_id = _session_id(client)
        response = client.post(
            f"/sessions/{session_id}/prompts",
            json={
                "prompt": "go",
                "inline_skills": ["demo-skill", "demo-skill"],
            },
        )

    assert response.status_code == 202
    assert response.json()["job"]["metadata"][JOB_INLINE_SKILLS_KEY] == ["demo-skill"]


def test_submit_prompt_rejects_an_unknown_skill(app):
    with TestClient(app) as client:
        session_id = _session_id(client)
        response = client.post(
            f"/sessions/{session_id}/prompts",
            json={"prompt": "go", "inline_skills": ["nonesuch"]},
        )
        jobs = client.get(f"/sessions/{session_id}/jobs").json()["jobs"]

    assert response.status_code == 400
    assert jobs == []


def test_submit_prompt_rejects_too_many_skills(app):
    with TestClient(app) as client:
        session_id = _session_id(client)
        response = client.post(
            f"/sessions/{session_id}/prompts",
            json={
                "prompt": "go",
                # Distinct names so the dedupe does not bring the count back
                # under the bound before it is checked.
                "inline_skills": [
                    f"demo-skill-{index}" for index in range(MAX_INLINE_SKILLS + 1)
                ],
            },
        )
        jobs = client.get(f"/sessions/{session_id}/jobs").json()["jobs"]

    assert response.status_code == 400
    assert jobs == []


def test_submit_prompt_ignores_a_forged_metadata_skill_list(app):
    with TestClient(app) as client:
        session_id = _session_id(client)
        response = client.post(
            f"/sessions/{session_id}/prompts",
            json={
                "prompt": "go",
                "metadata": {JOB_INLINE_SKILLS_KEY: ["../../etc/passwd"]},
            },
        )

    assert response.status_code == 202
    assert JOB_INLINE_SKILLS_KEY not in response.json()["job"]["metadata"]


def test_submit_prompt_keeps_other_metadata(app):
    with TestClient(app) as client:
        session_id = _session_id(client)
        response = client.post(
            f"/sessions/{session_id}/prompts",
            json={
                "prompt": "go",
                "metadata": {"source": "test"},
                "inline_skills": ["demo-skill"],
            },
        )

    assert response.status_code == 202
    assert response.json()["job"]["metadata"] == {
        "source": "test",
        JOB_INLINE_SKILLS_KEY: ["demo-skill"],
    }
