from __future__ import annotations

from agent_orchestrator.runtime.builtin_tools import is_master_job

from .builtin_tools_test_support import make_job, skill_registry


def test_is_master_job_true_for_prompt_without_parent():
    job = make_job(parent_job_id=None, job_type="prompt")
    assert is_master_job(job) is True


def test_is_master_job_false_for_child_job():
    job = make_job(parent_job_id="parent-id", job_type="prompt")
    assert is_master_job(job) is False


def test_is_master_job_false_for_compaction_job():
    job = make_job(parent_job_id=None, job_type="compaction")
    assert is_master_job(job) is False


def test_build_builtin_registry_includes_skill_loading_tools(skill_registry):
    from agent_orchestrator.runtime.builtin_tools import (
        BuiltinToolDefinition,
        BuiltinToolRegistry,
    )

    registry = BuiltinToolRegistry()
    registry.register(
        BuiltinToolDefinition(
            "load_skill",
            "desc",
            {"type": "object", "properties": {}, "required": []},
            lambda args: None,
        )
    )
    registry.register(
        BuiltinToolDefinition(
            "load_skill_reference",
            "desc",
            {"type": "object", "properties": {}, "required": []},
            lambda args: None,
        )
    )
    tools = registry.as_openai_tools()
    assert any(t["function"]["name"] == "load_skill" for t in tools)
    assert any(t["function"]["name"] == "load_skill_reference" for t in tools)


def test_spawn_subagent_absent_for_child_job(skill_registry):
    child_job = make_job(parent_job_id="parent-id", job_type="prompt")
    assert not is_master_job(child_job)


def test_spawn_subagent_absent_for_compaction_job(skill_registry):
    compaction_job = make_job(parent_job_id=None, job_type="compaction")
    assert not is_master_job(compaction_job)
