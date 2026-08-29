from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_orchestrator.runtime.prompt_run import (
    PromptRunService,
    extract_marvel_lcg_option_identity,
)
from agent_orchestrator.runtime.skills import SkillRegistry
from agent_orchestrator.runtime.system_prompts import build_subagent_system_prompt

REPO_ROOT = Path(__file__).resolve().parents[4]
ORCHESTRATOR_SKILL = REPO_ROOT / "skills" / "marvel-champions-orchestrator" / "SKILL.md"
PROMPT_CONTRACT = (
    REPO_ROOT
    / "skills"
    / "marvel-champions-orchestrator"
    / "references"
    / "player-turn-prompt.md"
)
RHINO_FIXTURE = (
    REPO_ROOT
    / "services"
    / "game-service"
    / "tests"
    / "unit"
    / "fixtures"
    / "rhino_normalization.json"
)


def test_player_prompt_contract_is_discoverable_from_orchestrator_skill() -> None:
    skill = ORCHESTRATOR_SKILL.read_text(encoding="utf-8")
    contract = PROMPT_CONTRACT.read_text(encoding="utf-8")

    assert "references/player-turn-prompt.md" in skill
    assert "AUTHORITATIVE STATE CHECKPOINT" in contract
    assert "CURRENT ENGINE PROMPT" in contract
    assert "game-service_get_game_state" in contract
    assert "game-service_list_game_options" in contract


def test_player_prompt_contract_has_no_coordinator_choice_coaching() -> None:
    contract = PROMPT_CONTRACT.read_text(encoding="utf-8").lower()

    assert "must attack" not in contract
    assert "must thwart" not in contract
    assert "recommended choice" not in contract
    assert "decline" not in contract
    assert "coordinator must not add a recommended action" in contract


def test_final_rhino_threat_sequence_stays_non_terminal_with_authoritative_hp() -> None:
    fixture = json.loads(RHINO_FIXTURE.read_text(encoding="utf-8"))
    checkpoints = fixture["checkpoints"]
    contract = PROMPT_CONTRACT.read_text(encoding="utf-8")

    threats = [
        checkpoint["world"]["area_schemes_main"][0]["info"]["k_threat"]
        for checkpoint in checkpoints
    ]
    villain_health = [
        checkpoint["world"]["area_villain"][0]["info"]["health"]
        for checkpoint in checkpoints
    ]

    assert threats == [9, 12, 14]
    assert villain_health == [19, 19, 19]
    assert "9/14" in contract
    assert "12/14" in contract
    assert "14/14" in contract
    assert "mode=in progress" in contract
    assert "MUST NOT turn that threat value into a defeated-villain outcome" in contract


def test_player_session_system_prompt_invalidates_persistent_facts() -> None:
    prompt = build_subagent_system_prompt(
        SkillRegistry(()), [], platform="marvel-lcg", player_session=True
    )

    assert "## Player-session state contract" in prompt
    assert "Earlier prompts, tool results" in prompt
    assert "discard those facts" in prompt
    assert "one fresh authoritative state read" in prompt
    assert "mode=win" in prompt
    assert "mode=loss" in prompt
    assert "villainHitPoints" in prompt


def test_player_session_turn_authority_is_platform_specific() -> None:
    dragncards_prompt = build_subagent_system_prompt(
        SkillRegistry(()),
        [],
        platform="dragncards",
        player_session=True,
    )
    marvel_lcg_prompt = build_subagent_system_prompt(
        SkillRegistry(()),
        [],
        platform="marvel-lcg",
        player_session=True,
    )
    dragncards_prompt = " ".join(dragncards_prompt.split())
    marvel_lcg_prompt = " ".join(marvel_lcg_prompt.split())

    assert (
        "absent `activeSeat`, `firstPlayer`, and `pendingSeats` metadata does not make"
        in (dragncards_prompt)
    )
    assert "coordinator owns the configured sequential seat order" in dragncards_prompt
    assert (
        "`pendingSeats` is engine-owned and must name your assigned seat"
        in marvel_lcg_prompt
    )
    assert "If it is absent, contradictory, or does not name you" in marvel_lcg_prompt
    assert (
        "coordinator owns the configured sequential seat order" not in marvel_lcg_prompt
    )


def _option_messages(options: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "list-call",
                    "function": {"name": "game-service_list_game_options"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "list-call",
            "content": json.dumps(
                {
                    "is_error": False,
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "event_name": "player_turn",
                                    "options": options,
                                }
                            ),
                        }
                    ],
                }
            ),
        },
    ]


def test_option_identity_uses_top_level_engine_event_when_option_omits_it() -> None:
    identity = extract_marvel_lcg_option_identity(
        tool_name="choose_game_option",
        arguments={"option_id": "option-7"},
        messages=_option_messages([{"id": "option-7", "name": "Play"}]),
    )

    assert identity == {"id": "option-7", "name": "Play", "event": "player_turn"}


def test_option_identity_prefers_option_event_over_top_level_engine_event() -> None:
    identity = extract_marvel_lcg_option_identity(
        tool_name="choose_game_option",
        arguments={"option_id": "option-7"},
        messages=_option_messages(
            [{"id": "option-7", "name": "Play", "event": "option_event"}]
        ),
    )

    assert identity == {"id": "option-7", "name": "Play", "event": "option_event"}


class _RecordingHistoryEmitter:
    enabled = True

    def __init__(self) -> None:
        self.kwargs: dict[str, object] | None = None

    async def emit_agent_move(self, **kwargs: object) -> None:
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_child_move_carries_server_set_coordinator_prompt_provenance() -> None:
    emitter = _RecordingHistoryEmitter()
    service = PromptRunService.__new__(PromptRunService)
    service._history_emitter = emitter
    service._history_tasks = set()

    session = SimpleNamespace(
        metadata_json={
            "player_id": "player1",
            "orchestrator_session_id": "orchestrator-1",
        }
    )
    tool_definition = SimpleNamespace(actual_name="choose_game_option")

    service._emit_agent_move_event(
        game_id="game-1",
        tool_definition=tool_definition,
        arguments={"option_id": "option-7"},
        reasoning="",
        messages=[],
        session=session,
        prompt="AUTHORITATIVE STATE CHECKPOINT ...",
        job_id="child-job-1",
        parent_job_id="parent-job-1",
    )
    await service._history_tasks.pop()

    assert emitter.kwargs is not None
    assert emitter.kwargs["prompt_provenance"] == {
        "source": "coordinator",
        "prompt": "AUTHORITATIVE STATE CHECKPOINT ...",
        "orchestrator_session_id": "orchestrator-1",
        "parent_job_id": "parent-job-1",
        "child_job_id": "child-job-1",
    }


def test_non_player_subagents_do_not_receive_player_session_contract() -> None:
    prompt = build_subagent_system_prompt(SkillRegistry(()), [])

    assert "## Player-session state contract" not in prompt
