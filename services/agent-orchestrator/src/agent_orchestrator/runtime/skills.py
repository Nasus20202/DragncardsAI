from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Job metadata key holding the skills a prompt loads into its own turn. The
# prompt endpoint writes only validated names here, so the worker can render
# them without re-checking the client.
JOB_INLINE_SKILLS_KEY = "inline_skills"

# How many skills one prompt may load. A `SKILL.md` is thousands of tokens, and
# a message that needs more than a handful at once is a mistake rather than a
# use case.
MAX_INLINE_SKILLS = 4

_INLINE_SKILL_PREAMBLE = (
    "The user loaded the following skill(s) into this message. Their full"
    " instructions are already below — do not call `load_skill` for them again."
    " Use `load_skill_reference(<skill_name>, <reference_name>)` if you need one"
    " of the reference files each skill lists."
)


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


def reference_files_under(skill_path: Path) -> list[str]:
    """The markdown references of the skill at ``skill_path``, sorted.

    Takes a PATH rather than a skill name so a caller that already holds the
    definition does not pay a full re-scan of every skill root to get back to it.

    Symlinks are left out because `load_reference_content` refuses them — a link
    out of the skill fails its containment check, and a link within the skill
    resolves to a name other than the one it was asked for. Listing one would
    advertise a reference that cannot then be loaded.
    """
    return sorted(
        ref_file.relative_to(skill_path).as_posix()
        for ref_file in skill_path.rglob("*.md")
        if ref_file.is_file()
        and not ref_file.is_symlink()
        and ref_file.name != "SKILL.md"
    )


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
        return reference_files_under(self._skill_path(skill_name))

    def load_reference_content(self, skill_name: str, reference_name: str) -> str:
        skill_path = self._skill_path(skill_name).resolve()
        try:
            reference_path = (skill_path / reference_name).resolve()
            normalized_reference = reference_path.relative_to(skill_path).as_posix()
        except ValueError:
            # ValueError covers two unrelated cases, both of which mean "no such
            # reference": `relative_to` on a path outside the skill, and the
            # `lstat: embedded null character` that `resolve()` raises for a name
            # holding a null byte. Letting the latter escape used to fail the
            # whole job rather than just the tool call.
            raise FileNotFoundError(reference_name) from None
        except OSError:
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


def dedupe_skill_names(skill_names: Sequence[str]) -> list[str]:
    """The given names with repeats dropped, first occurrence winning."""
    return list(dict.fromkeys(skill_names))


def render_prompt_with_inline_skills(
    registry: SkillRegistry,
    skill_names: Sequence[str],
    prompt: str,
) -> tuple[str, list[str]]:
    """
    The user message for a turn whose prompt loaded skills into itself.

    Each named skill contributes exactly what `load_skill` would have returned —
    `SKILL.md` plus the inventory of its reference files — placed ahead of the
    text the user typed, so the instructions are in context on the turn that
    asked for them instead of after a tool round trip.

    Only the message handed to the model changes: the job's stored prompt stays
    the typed text, which is what the transcript shows and what a later turn
    replays, so a mention costs its tokens once.

    A name that no longer resolves on disk is skipped rather than failing the
    job — the skill directory may have gone away between submission and
    execution. Returns the message and the names actually rendered.
    """
    blocks: list[str] = []
    loaded: list[str] = []
    for skill_name in dedupe_skill_names(skill_names):
        try:
            content = registry.load_skill_content(skill_name)
        except FileNotFoundError, OSError:
            continue
        blocks.append(f"## Skill: {skill_name}\n\n{content}")
        loaded.append(skill_name)

    if not blocks:
        return prompt, []

    return (
        "\n\n".join([_INLINE_SKILL_PREAMBLE, *blocks, "---", prompt]),
        loaded,
    )
