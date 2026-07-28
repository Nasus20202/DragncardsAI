from __future__ import annotations

from pathlib import Path

import pytest

from eval_service.config import Settings
from eval_service.judge.config import (
    ResolvedJudgeConfig,
    ResolvedReasoning,
    SkillResolver,
    UnknownSkillError,
    resolve_judge_config,
)
from eval_service.judge.prompt import build_move_messages
from eval_service.schemas.api import JudgeConfig, JudgeReasoning


def _settings(**overrides) -> Settings:
    # `eval_judge_provider` is pinned empty so the tests below exercise the
    # "provider derived from the model id" path deterministically, whatever a
    # developer has EVAL_JUDGE_PROVIDER set to.
    base = dict(eval_judge_model="anthropic/claude-default", eval_judge_provider="")
    base.update(overrides)
    return Settings(**base)


def _make_skill(root: Path, name: str, body: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: d\n---\n{body}\n", encoding="utf-8"
    )


def _resolver(tmp_path: Path) -> SkillResolver:
    return SkillResolver((tmp_path,))


def test_defaults_used_when_judge_omitted(tmp_path):
    resolved = resolve_judge_config(_settings(), None, _resolver(tmp_path))
    assert resolved.model == "anthropic/claude-default"
    assert resolved.provider == "anthropic"
    assert resolved.reasoning.enabled is False
    assert resolved.prompt_override is None
    assert resolved.skills == ()


def test_request_overrides_model_provider_reasoning(tmp_path):
    requested = JudgeConfig(
        provider_id="openrouter",
        model_name="openrouter/google/gemma:free",
        reasoning=JudgeReasoning(enabled=True, effort="high", max_tokens=512),
        prompt_override="custom rubric",
    )
    resolved = resolve_judge_config(_settings(), requested, _resolver(tmp_path))
    assert resolved.model == "openrouter/google/gemma:free"
    assert resolved.provider == "openrouter"
    assert resolved.reasoning == ResolvedReasoning(
        enabled=True, effort="high", max_tokens=512
    )
    assert resolved.prompt_override == "custom rubric"


def test_partial_override_falls_back_to_defaults(tmp_path):
    # Only model overridden; provider derived from default provider setting.
    requested = JudgeConfig(model_name="openrouter/x/y")
    resolved = resolve_judge_config(
        _settings(eval_judge_provider="anthropic"), requested, _resolver(tmp_path)
    )
    assert resolved.model == "openrouter/x/y"
    assert resolved.provider == "anthropic"


def test_default_reasoning_from_env(tmp_path):
    settings = _settings(
        eval_judge_reasoning_enabled=True, eval_judge_reasoning_effort="low"
    )
    resolved = resolve_judge_config(settings, JudgeConfig(), _resolver(tmp_path))
    assert resolved.reasoning.enabled is True
    assert resolved.reasoning.effort == "low"


def test_reasoning_gateway_options_mapping():
    disabled = ResolvedReasoning(enabled=False, effort="high")
    assert disabled.to_gateway_options() == {}
    enabled = ResolvedReasoning(enabled=True, effort="medium", max_tokens=256)
    assert enabled.to_gateway_options() == {
        "reasoning": {"effort": "medium", "max_tokens": 256}
    }
    no_max = ResolvedReasoning(enabled=True, effort="low")
    assert no_max.to_gateway_options() == {"reasoning": {"effort": "low"}}


def test_known_skill_resolves(tmp_path):
    _make_skill(tmp_path, "rules", "the rules body")
    requested = JudgeConfig(skills=["rules"])
    resolved = resolve_judge_config(_settings(), requested, _resolver(tmp_path))
    assert resolved.skills == ("rules",)


def test_unknown_skill_raises(tmp_path):
    _make_skill(tmp_path, "rules", "body")
    requested = JudgeConfig(skills=["rules", "nope"])
    with pytest.raises(UnknownSkillError) as exc:
        resolve_judge_config(_settings(), requested, _resolver(tmp_path))
    assert "nope" in str(exc.value)


def test_skill_markdown_injected_into_prompt(tmp_path):
    _make_skill(tmp_path, "rules", "RULESBODY-XYZ")
    skills = _resolver(tmp_path).load_markdown(("rules",))
    from eval_service.judge.assembly import MoveInput

    move = MoveInput(
        game_id="g1",
        target_seq=2,
        intended_action="play",
        reasoning="",
        arguments={},
        prior_state={},
        resulting_state={},
    )
    messages = build_move_messages(move, prompt_override="OVERRIDE", skills=skills)
    system = messages[0]["content"]
    assert "OVERRIDE" in system
    assert "RULESBODY-XYZ" in system
    assert "Skill: rules" in system


def test_resolved_config_json_roundtrip():
    cfg = ResolvedJudgeConfig(
        model="m",
        provider="p",
        reasoning=ResolvedReasoning(enabled=True, effort="high", max_tokens=10),
        prompt_override="po",
        skills=("a", "b"),
    )
    again = ResolvedJudgeConfig.from_json(cfg.to_json())
    assert again == cfg
    assert ResolvedJudgeConfig.from_json(None) is None


def test_default_skill_root_points_at_repo_skills():
    settings = Settings(eval_judge_model="x")
    roots = settings.skill_root_paths
    assert len(roots) == 1
    assert roots[0].name == "skills"
