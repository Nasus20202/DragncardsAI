"""Unit tests for the shared context estimator.

The auto-compaction trigger and the context metadata endpoint both read their
number off `estimate_request`. These tests pin what that function counts, so a
component quietly dropped from one caller cannot pass as agreement.
"""

from __future__ import annotations

from pathlib import Path

from agent_orchestrator.runtime.context_estimate import estimate_request
from agent_orchestrator.runtime.skills import (
    SkillRegistry,
    render_prompt_with_inline_skills,
)
from agent_orchestrator.runtime.tokens import (
    estimate_tokens_for_messages,
    estimate_tokens_for_tools,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "next_step",
            "description": "Advance the game",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]
REPLAY = [
    {"role": "user", "content": "take your turn"},
    {"role": "assistant", "content": "thwip"},
]


def test_estimate_counts_every_part_of_the_request():
    estimate = estimate_request(
        system_prompt="you are an agent",
        tools=TOOLS,
        replay_messages=REPLAY,
        user_message="next turn",
        context_window_size=128_000,
    )

    assert estimate.system_prompt == estimate_tokens_for_messages(
        [{"role": "system", "content": "you are an agent"}]
    )
    assert estimate.tools == estimate_tokens_for_tools(TOOLS)
    assert estimate.replay == estimate_tokens_for_messages(REPLAY)
    assert estimate.user_message == estimate_tokens_for_messages(
        [{"role": "user", "content": "next turn"}]
    )
    assert estimate.total == (
        estimate.system_prompt
        + estimate.tools
        + estimate.replay
        + estimate.user_message
    )
    assert estimate.usage_ratio == estimate.total / 128_000


def test_fixed_cost_is_everything_compaction_cannot_shrink():
    estimate = estimate_request(
        system_prompt="you are an agent",
        tools=TOOLS,
        replay_messages=REPLAY,
        user_message="next turn",
        context_window_size=128_000,
    )
    assert estimate.fixed_cost == estimate.total - estimate.replay


def test_the_replay_alone_understates_the_request():
    """The defect this estimator exists to close, stated as an inequality.

    A trigger that measures the replay alone sees a smaller number than the
    request it is deciding about, by exactly the fixed cost.
    """
    estimate = estimate_request(
        system_prompt="you are an agent",
        tools=TOOLS,
        replay_messages=REPLAY,
        user_message="next turn",
        context_window_size=128_000,
    )
    replay_only_ratio = estimate.replay / 128_000
    assert replay_only_ratio < estimate.usage_ratio
    assert estimate.total - estimate.replay == estimate.fixed_cost


def test_reported_ratio_is_clamped_and_rounded():
    estimate = estimate_request(
        system_prompt="you are an agent",
        tools=TOOLS,
        replay_messages=REPLAY,
        user_message=None,
        context_window_size=10,
    )
    assert estimate.usage_ratio > 1.0
    assert estimate.reported_usage_ratio == 1.0


def test_zero_window_does_not_divide_by_zero():
    estimate = estimate_request(
        system_prompt="",
        tools=[],
        replay_messages=[],
        context_window_size=0,
    )
    assert estimate.usage_ratio == 0.0
    assert estimate.reported_usage_ratio == 0.0


def test_breakdown_omits_the_user_message():
    """The endpoint's breakdown reports a session at rest.

    There is no current turn when a session is merely being looked at, so a
    user-message row there would always read zero. The trigger reports it on
    its log line instead.
    """
    estimate = estimate_request(
        system_prompt="you are an agent",
        tools=TOOLS,
        replay_messages=REPLAY,
        user_message="next turn",
        context_window_size=128_000,
    )
    assert set(estimate.as_breakdown()) == {"system_prompt", "replay", "tools"}


def test_a_skill_inlined_into_the_prompt_raises_the_estimate(tmp_path: Path):
    """DRA-15's inlined `SKILL.md` is what made the gap material.

    The stored prompt is the text the user typed; the message the model gets
    carries the skill as well. The estimate has to cost the second one.
    """
    root = tmp_path / "skills"
    (root / "big-skill").mkdir(parents=True)
    (root / "big-skill" / "SKILL.md").write_text(
        "rules and procedures. " * 2000, encoding="utf-8"
    )
    registry = SkillRegistry((root,))

    typed = "take your turn"
    rendered, loaded = render_prompt_with_inline_skills(registry, ["big-skill"], typed)
    assert loaded == ["big-skill"]

    without = estimate_request(
        system_prompt="",
        tools=[],
        replay_messages=[],
        user_message=typed,
        context_window_size=128_000,
    )
    with_skill = estimate_request(
        system_prompt="",
        tools=[],
        replay_messages=[],
        user_message=rendered,
        context_window_size=128_000,
    )

    assert with_skill.user_message > without.user_message + 1000
    assert with_skill.total > without.total
