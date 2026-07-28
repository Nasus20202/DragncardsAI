"""Shared validation for a stored configuration that names skills.

Both a per-seat player configuration and a persona name skills that a child
session will have enabled at spawn time, and both need the same two things: the
skill must resolve in the on-disk catalogue, and it must exist as a
``skill_registries`` row before a child can be assigned it. Without the second
step a skill only this configuration uses is silently dropped when its child
starts, because the session/skill join is a foreign key.
"""

from __future__ import annotations

from fastapi import HTTPException

from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.storage.repository import Repository


async def validate_and_register_skills(
    skill_names: list[str],
    *,
    registry: SkillRegistry,
    repo: Repository,
) -> None:
    """Reject any unresolvable skill by name, then register the rest globally.

    Raises ``HTTPException(400)`` naming the first skill that cannot be resolved,
    so a caller learns *which* skill was wrong rather than that something was.
    """
    for skill_name in skill_names:
        definition = registry.resolve(skill_name)
        if definition is None:
            raise HTTPException(status_code=400, detail=f"Unknown skill: {skill_name}")
        await repo.add_skill_registry(
            name=skill_name,
            skill_path=str(definition.path),
            description=definition.description,
            metadata_json={},
        )
