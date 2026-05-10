from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    path: Path


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
                    discovered[candidate.name] = SkillDefinition(
                        name=candidate.name,
                        path=candidate,
                    )
        return discovered

    def resolve(self, skill_name: str) -> SkillDefinition | None:
        return self.list_skills().get(skill_name)

    def load_markdown(self, skill_name: str) -> str:
        definition = self.resolve(skill_name)
        if definition is None:
            raise FileNotFoundError(skill_name)
        return (definition.path / "SKILL.md").read_text(encoding="utf-8")
