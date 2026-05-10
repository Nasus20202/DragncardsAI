from __future__ import annotations

from pathlib import Path

from agent_orchestrator.runtime.skills import SkillRegistry


def test_skill_registry_discovers_skill(tmp_path: Path):
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("demo", encoding="utf-8")

    registry = SkillRegistry((tmp_path,))

    discovered = registry.list_skills()
    assert "demo-skill" in discovered
    assert registry.load_markdown("demo-skill") == "demo"
