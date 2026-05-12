from __future__ import annotations

from typing import Any

from agent_orchestrator.runtime.skills import SkillRegistry

BASE_SYSTEM_PROMPT_PARTS = (
    "You are an agent orchestrator for DragnCardsAI.",
    "Use available MCP tools when they are necessary to answer or act.",
    "When using tools, rely on the provided function schema.",
)


def build_system_prompt(skill_registry: SkillRegistry, assignments: list[Any]) -> str:
    parts = list(BASE_SYSTEM_PROMPT_PARTS)
    skill_blocks: list[str] = []
    for assignment in assignments:
        try:
            definition = skill_registry.resolve(assignment.skill_name)
            if definition is None:
                continue
            description = definition.description or skill_registry.get_summary(
                assignment.skill_name
            )
        except FileNotFoundError:
            continue
        block_lines = [f"### {assignment.skill_name}", f"{description}"]
        if definition.metadata:
            meta_lines = "\n".join(
                f"- {k}: {v}" for k, v in definition.metadata.items()
            )
            block_lines.append(f"**Metadata:**\n{meta_lines}")
        skill_blocks.append("\n\n".join(block_lines))
    if skill_blocks:
        skills_section = "## Available skills\n\n" + "\n\n---\n\n".join(skill_blocks)
        skills_section += (
            "\n\n---\n\nBefore using a skill, call `load_skill(<name>)` to load `SKILL.md` "
            "and see available references. If you need one of those references, call "
            "`load_skill_reference(<skill_name>, <reference_name>)` for the specific file."
        )
        parts.append(skills_section)
    return "\n\n".join(parts)
