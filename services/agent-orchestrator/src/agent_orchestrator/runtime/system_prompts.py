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
    for assignment in assignments:
        try:
            content = skill_registry.load_markdown(assignment.skill_name)
        except FileNotFoundError:
            continue
        parts.append(f"Skill {assignment.skill_name}:\n{content}")
    return "\n\n".join(parts)
