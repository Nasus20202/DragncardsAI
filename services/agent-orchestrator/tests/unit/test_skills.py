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


def test_get_summary_returns_first_non_blank_non_heading_line(tmp_path: Path):
    skill_dir = tmp_path / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "# My Skill\n\nThis is the summary line.\n\nMore content.",
        encoding="utf-8",
    )
    registry = SkillRegistry((tmp_path,))
    assert registry.get_summary("my-skill") == "This is the summary line."


def test_get_summary_falls_back_to_skill_name_when_no_content(tmp_path: Path):
    skill_dir = tmp_path / "empty-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Only A Heading\n", encoding="utf-8")
    registry = SkillRegistry((tmp_path,))
    assert registry.get_summary("empty-skill") == "empty-skill"


def test_load_skill_content_without_reference_dir(tmp_path: Path):
    skill_dir = tmp_path / "simple-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    registry = SkillRegistry((tmp_path,))
    assert registry.load_skill_content("simple-skill") == "Skill body."


def test_load_skill_content_with_nested_markdown_files(tmp_path: Path):
    skill_dir = tmp_path / "rich-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    ref_dir = skill_dir / "reference"
    ref_dir.mkdir()
    (ref_dir / "guide.md").write_text("Guide content.", encoding="utf-8")
    (ref_dir / "rules.md").write_text("Rules content.", encoding="utf-8")
    registry = SkillRegistry((tmp_path,))
    content = registry.load_skill_content("rich-skill")
    assert "Skill body." in content
    assert "## Available references" in content
    assert "- reference/guide.md" in content
    assert "- reference/rules.md" in content
    assert "Guide content." not in content
    assert "Rules content." not in content


def test_list_reference_files_returns_sorted_markdown_paths(tmp_path: Path):
    skill_dir = tmp_path / "rich-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    ref_dir = skill_dir / "reference"
    ref_dir.mkdir()
    (ref_dir / "zeta.md").write_text("Zeta.", encoding="utf-8")
    (ref_dir / "alpha.md").write_text("Alpha.", encoding="utf-8")
    (ref_dir / "notes.txt").write_text("Ignore.", encoding="utf-8")
    nested_dir = skill_dir / "docs"
    nested_dir.mkdir()
    (nested_dir / "beta.md").write_text("Beta.", encoding="utf-8")

    registry = SkillRegistry((tmp_path,))

    assert registry.list_reference_files("rich-skill") == [
        "docs/beta.md",
        "reference/alpha.md",
        "reference/zeta.md",
    ]


def test_load_reference_content_reads_named_markdown_reference(tmp_path: Path):
    skill_dir = tmp_path / "rich-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    ref_dir = skill_dir / "reference"
    ref_dir.mkdir()
    (ref_dir / "guide.md").write_text("Guide content.", encoding="utf-8")

    registry = SkillRegistry((tmp_path,))

    assert (
        registry.load_reference_content("rich-skill", "reference/guide.md")
        == "Guide content."
    )


def test_reference_files_include_markdown_next_to_skill_md(tmp_path: Path):
    skill_dir = tmp_path / "rules-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    (skill_dir / "alpha.md").write_text("Alpha.", encoding="utf-8")
    (skill_dir / "beta.md").write_text("Beta.", encoding="utf-8")

    registry = SkillRegistry((tmp_path,))

    assert registry.list_reference_files("rules-skill") == ["alpha.md", "beta.md"]
    assert registry.load_reference_content("rules-skill", "beta.md") == "Beta."
    content = registry.load_skill_content("rules-skill")
    assert "## Available references" in content
    assert "- alpha.md" in content
    assert "- beta.md" in content


def test_load_reference_content_rejects_path_traversal(tmp_path: Path):
    skill_dir = tmp_path / "rules-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    (skill_dir / "alpha.md").write_text("Alpha.", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("Outside.", encoding="utf-8")

    registry = SkillRegistry((tmp_path,))

    try:
        registry.load_reference_content("rules-skill", "../outside.md")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Expected FileNotFoundError for path traversal")


def test_load_reference_content_refuses_a_null_byte_without_raising(tmp_path: Path):
    """`resolve()` raises ValueError, not OSError, for an embedded null byte.

    It used to escape `load_reference_content` entirely, past the tool handler's
    `except FileNotFoundError`, and fail the whole job rather than the one tool
    call. eval-service hit the same bug and fixed it; this is the back-port.
    """
    skill_dir = tmp_path / "rules-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    (skill_dir / "alpha.md").write_text("Alpha.", encoding="utf-8")

    registry = SkillRegistry((tmp_path,))

    for hostile in ("alpha\x00.md", "\x00alpha.md", "a" * 5000 + ".md"):
        try:
            registry.load_reference_content("rules-skill", hostile)
        except FileNotFoundError:
            pass
        else:
            raise AssertionError(f"expected FileNotFoundError for {hostile!r}")


def test_list_reference_files_omits_symlinks_it_could_not_load(tmp_path: Path):
    """The catalogue must not advertise a reference the loader refuses.

    A symlink out of the skill fails containment; a symlink within it resolves to
    a name other than the one asked for. Either way `load_reference_content`
    refuses, so listing one would offer a dead entry to whoever renders it.
    """
    skill_dir = tmp_path / "rules-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("Skill body.", encoding="utf-8")
    real = skill_dir / "alpha.md"
    real.write_text("Alpha.", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("Outside.", encoding="utf-8")
    (skill_dir / "leak.md").symlink_to(outside)
    (skill_dir / "alias.md").symlink_to(real)

    registry = SkillRegistry((tmp_path,))

    listed = registry.list_reference_files("rules-skill")
    assert listed == ["alpha.md"]
    # Everything listed loads.
    for name in listed:
        registry.load_reference_content("rules-skill", name)
