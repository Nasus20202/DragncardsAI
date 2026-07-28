from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def enabled_skill_assignments(assignments: list[Any]) -> list[Any]:
    """
    Keep only the assignments a session currently has switched on.

    A `SessionEnabledSkill` row is a soft toggle: disabling a skill flips
    `enabled` instead of deleting the row, so every consumer that turns
    assignments into agent-visible behaviour must filter on the flag.
    """
    return [
        assignment
        for assignment in assignments or []
        if getattr(assignment, "enabled", True)
    ]


def _parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    """
    Extract YAML frontmatter from a markdown string.
    Returns (frontmatter_dict, body_without_frontmatter).
    Falls back to ({}, content) if no frontmatter is present.
    """
    if not content.startswith("---"):
        return {}, content

    end = content.find("\n---", 3)
    if end == -1:
        return {}, content

    fm_block = content[3:end].strip()
    body = content[end + 4 :].lstrip("\n")

    parsed: dict[str, object] = {}
    # Minimal YAML parser — handles simple key: value and nested mappings one level deep
    current_key: str | None = None
    for line in fm_block.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if line.startswith("  ") and current_key is not None:
            # Nested key under current_key
            sub = line.strip()
            if ":" in sub:
                k, _, v = sub.partition(":")
                nested = parsed.setdefault(current_key, {})
                if isinstance(nested, dict):
                    nested[k.strip()] = v.strip().strip('"')
        elif ":" in line:
            k, _, v = line.partition(":")
            current_key = k.strip()
            val = v.strip().strip('"')
            if val:
                parsed[current_key] = val
            else:
                parsed[current_key] = {}
    return parsed, body


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: Path
    description: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class SkillRegistry:
    def __init__(self, roots: tuple[Path, ...]):
        self._roots = roots

    def list_skills(self) -> dict[str, SkillDefinition]:
        discovered: dict[str, SkillDefinition] = {}
        for root in self._roots:
            if not root.exists():
                continue
            for candidate in root.iterdir():
                if not candidate.is_dir():
                    continue
                skill_file = candidate / "SKILL.md"
                if skill_file.exists():
                    raw = skill_file.read_text(encoding="utf-8")
                    fm, _ = _parse_frontmatter(raw)
                    description = str(fm.get("description", ""))
                    raw_meta = fm.get("metadata", {})
                    metadata = (
                        {k: str(v) for k, v in raw_meta.items()}
                        if isinstance(raw_meta, dict)
                        else {}
                    )
                    discovered[candidate.name] = SkillDefinition(
                        name=candidate.name,
                        path=candidate,
                        description=description,
                        metadata=metadata,
                    )
        return discovered

    def resolve(self, skill_name: str) -> SkillDefinition | None:
        return self.list_skills().get(skill_name)

    def load_markdown(self, skill_name: str) -> str:
        definition = self.resolve(skill_name)
        if definition is None:
            raise FileNotFoundError(skill_name)
        return (definition.path / "SKILL.md").read_text(encoding="utf-8")

    def _skill_path(self, skill_name: str) -> Path:
        definition = self.resolve(skill_name)
        if definition is None:
            raise FileNotFoundError(skill_name)
        return definition.path

    def list_reference_files(self, skill_name: str) -> list[str]:
        skill_path = self._skill_path(skill_name)
        return sorted(
            ref_file.relative_to(skill_path).as_posix()
            for ref_file in skill_path.rglob("*.md")
            if ref_file.is_file() and ref_file.name != "SKILL.md"
        )

    def load_reference_content(self, skill_name: str, reference_name: str) -> str:
        skill_path = self._skill_path(skill_name).resolve()
        reference_path = (skill_path / reference_name).resolve()
        try:
            normalized_reference = reference_path.relative_to(skill_path).as_posix()
        except ValueError:
            raise FileNotFoundError(reference_name) from None
        if (
            reference_path.suffix != ".md"
            or normalized_reference != reference_name
            or not reference_path.is_file()
            or reference_path.name == "SKILL.md"
        ):
            raise FileNotFoundError(reference_name)
        return reference_path.read_text(encoding="utf-8")

    def get_summary(self, skill_name: str) -> str:
        """Return description from frontmatter, or first non-blank non-heading body line."""
        definition = self.resolve(skill_name)
        if definition is None:
            raise FileNotFoundError(skill_name)
        if definition.description:
            return definition.description
        content = self.load_markdown(skill_name)
        _, body = _parse_frontmatter(content)
        for line in body.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return skill_name

    def load_skill_content(self, skill_name: str) -> str:
        """Return SKILL.md followed by an inventory of available markdown references."""
        definition = self.resolve(skill_name)
        if definition is None:
            raise FileNotFoundError(skill_name)
        skill_markdown = (definition.path / "SKILL.md").read_text(encoding="utf-8")
        references = self.list_reference_files(skill_name)
        if not references:
            return skill_markdown

        reference_lines = ["## Available references", ""]
        reference_lines.extend(f"- {reference_name}" for reference_name in references)
        return f"{skill_markdown}\n\n" + "\n".join(reference_lines)
