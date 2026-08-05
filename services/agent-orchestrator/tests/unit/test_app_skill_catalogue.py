"""The skill catalogue reports each skill's reference files.

A consumer choosing references for a judge (or showing an agent what a skill
holds) has no other way to learn the names `load_skill_reference` accepts, so the
catalogue reports them. The names are reported even when there are none, as an
empty list, so nobody has to tell "no references" apart from "not reported".
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _catalogue(app) -> dict[str, dict]:
    with TestClient(app) as client:
        response = client.get("/skills")
    assert response.status_code == 200
    return {skill["name"]: skill for skill in response.json()["skills"]}


def test_a_skill_without_references_reports_an_empty_list(app):
    assert _catalogue(app)["demo-skill"]["references"] == []


def test_a_skill_reports_its_reference_files(app, tmp_path: Path):
    skill = tmp_path / "skills" / "demo-skill"
    (skill / "resources").mkdir(parents=True, exist_ok=True)
    (skill / "resources" / "errata.md").write_text("errata", encoding="utf-8")
    (skill / "guide.md").write_text("guide", encoding="utf-8")
    # Not markdown, and the skill's own summary: neither is a reference.
    (skill / "notes.txt").write_text("notes", encoding="utf-8")

    assert _catalogue(app)["demo-skill"]["references"] == [
        "guide.md",
        "resources/errata.md",
    ]
