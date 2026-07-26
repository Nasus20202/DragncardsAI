from __future__ import annotations

import json

import httpx
import pytest

from eval_service.integrations.bifrost import BifrostError, BifrostJudgeClient
from eval_service.judge.assembly import MoveInput, RoundInput
from eval_service.judge.config import ResolvedJudgeConfig, ResolvedReasoning
from eval_service.judge.parse import VerdictParseError, parse_verdict
from eval_service.judge.prompt import build_move_messages, build_round_messages
from eval_service.judge.writeback import (
    build_verdict_envelope,
    verdict_idempotency_key,
)


def _config(**overrides) -> ResolvedJudgeConfig:
    base = dict(
        model="anthropic/claude-x",
        provider="anthropic",
        reasoning=ResolvedReasoning(enabled=False, effort="medium", max_tokens=None),
        prompt_override=None,
        skills=(),
    )
    base.update(overrides)
    return ResolvedJudgeConfig(**base)


def test_parse_verdict_produces_structured_payload():
    response = json.dumps(
        {
            "scores": {
                "rules_legality": 9,
                "strategic_quality": 5,
                "tempo_efficiency": 8,
                "threat_resource": 6,
            },
            "overall_score": 7,
            "rationale": "Reasonable.",
            "flags": ["wasted_resource"],
        }
    )
    verdict = parse_verdict(
        response,
        scope="move",
        target_seq=12,
        round_span=None,
        model="anthropic/claude-x",
        provider="anthropic",
        evaluator_version="eval-1",
    )
    assert verdict.scores.rules_legality == 9
    assert verdict.overall_score == 7
    assert verdict.flags == ["wasted_resource"]
    assert verdict.evaluator.model == "anthropic/claude-x"
    assert verdict.evaluator.evaluator_version == "eval-1"


def test_parse_verdict_clamps_and_extracts_embedded_json():
    response = "Sure! Here is the verdict:\n" + json.dumps(
        {
            "scores": {
                "rules_legality": 99,
                "strategic_quality": -3,
                "tempo_efficiency": 5,
                "threat_resource": 5,
            },
            "overall_score": 12,
            "rationale": "x",
        }
    )
    verdict = parse_verdict(
        response,
        scope="move",
        target_seq=1,
        round_span=None,
        model="m",
        provider="p",
        evaluator_version="eval-1",
    )
    assert verdict.scores.rules_legality == 10
    assert verdict.scores.strategic_quality == 0
    assert verdict.overall_score == 10


def test_parse_verdict_rejects_missing_scores():
    with pytest.raises(VerdictParseError):
        parse_verdict(
            "no json here",
            scope="move",
            target_seq=1,
            round_span=None,
            model="m",
            provider="p",
            evaluator_version="eval-1",
        )


def test_parse_verdict_unwraps_language_hinted_fence():
    # A ```json fenced block whose rationale itself contains backticks must be
    # parsed by unwrapping the fence body, NOT by stripping all backticks.
    inner = json.dumps(
        {
            "scores": {
                "rules_legality": 6,
                "strategic_quality": 6,
                "tempo_efficiency": 6,
                "threat_resource": 6,
            },
            "overall_score": 6,
            "rationale": "Played `Quincarrier` for tempo.",
            "flags": [],
        }
    )
    response = f"Here you go:\n```json\n{inner}\n```\nDone."
    verdict = parse_verdict(
        response,
        scope="move",
        target_seq=3,
        round_span=None,
        model="m",
        provider="p",
        evaluator_version="eval-1",
    )
    assert verdict.overall_score == 6
    assert "`Quincarrier`" in verdict.rationale


def test_idempotency_key_is_stable_and_scoped():
    k1 = verdict_idempotency_key("g1", 12, "move", "eval-1")
    k2 = verdict_idempotency_key("g1", 12, "move", "eval-1")
    k3 = verdict_idempotency_key("g1", 12, "round", "eval-1")
    k4 = verdict_idempotency_key("g1", 12, "move", "eval-2")
    assert k1 == k2
    assert k1 != k3 != k4
    assert len(k1) == 64  # sha256 hex


def test_idempotency_key_same_config_is_stable():
    # Two distinct-but-equal configs must yield the SAME key (identical re-eval
    # still dedupes).
    cfg_a = _config()
    cfg_b = _config()
    assert verdict_idempotency_key(
        "g1", 12, "move", "eval-1", cfg_a
    ) == verdict_idempotency_key("g1", 12, "move", "eval-1", cfg_b)


def test_idempotency_key_invariant_to_skills_order():
    # The same skill SET in a different order is semantically identical, so it
    # must hash to the same key: a re-eval with reordered skills must NOT produce
    # a spurious second history event.
    ab = _config(skills=("alpha", "beta"))
    ba = _config(skills=("beta", "alpha"))
    assert verdict_idempotency_key(
        "g1", 12, "move", "eval-1", ab
    ) == verdict_idempotency_key("g1", 12, "move", "eval-1", ba)
    # A genuinely different skill set still yields a distinct key.
    ac = _config(skills=("alpha", "gamma"))
    assert verdict_idempotency_key(
        "g1", 12, "move", "eval-1", ab
    ) != verdict_idempotency_key("g1", 12, "move", "eval-1", ac)


def test_idempotency_key_differs_on_model_provider_prompt_skills_reasoning():
    base = verdict_idempotency_key("g1", 12, "move", "eval-1", _config())
    variants = {
        "model": _config(model="openai/gpt-z"),
        "provider": _config(provider="openai"),
        "prompt": _config(prompt_override="Be extra strict."),
        "skills": _config(skills=("marvel-rules",)),
        "reasoning": _config(
            reasoning=ResolvedReasoning(enabled=True, effort="high", max_tokens=None)
        ),
    }
    keys = {
        name: verdict_idempotency_key("g1", 12, "move", "eval-1", cfg)
        for name, cfg in variants.items()
    }
    # Every variant differs from the base AND from each other.
    for name, key in keys.items():
        assert key != base, f"{name} should change the key"
    assert len(set(keys.values())) == len(keys)


def test_idempotency_key_none_config_differs_from_a_config():
    # No-config (legacy) is a stable sentinel distinct from any real config.
    assert verdict_idempotency_key(
        "g1", 12, "move", "eval-1", None
    ) != verdict_idempotency_key("g1", 12, "move", "eval-1", _config())


def test_writeback_envelope_uses_evaluator_actor():
    verdict = parse_verdict(
        json.dumps(
            {
                "scores": {
                    "rules_legality": 5,
                    "strategic_quality": 5,
                    "tempo_efficiency": 5,
                    "threat_resource": 5,
                },
                "overall_score": 5,
                "rationale": "x",
                "flags": [],
            }
        ),
        scope="move",
        target_seq=12,
        round_span=None,
        model="m",
        provider="p",
        evaluator_version="eval-1",
    )
    envelope = build_verdict_envelope("g1", verdict)
    assert envelope["actor"] == "evaluator"
    assert envelope["event_type"] == "evaluation"
    assert envelope["payload"]["target_seq"] == 12
    assert envelope["idempotency_key"] == verdict_idempotency_key(
        "g1", 12, "move", "eval-1"
    )


@pytest.mark.asyncio
async def test_judge_routes_under_dedicated_identity_fresh_session():
    """The judge sends only the prompt under the dedicated bearer key."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"ok": True})}}]},
        )

    transport = httpx.MockTransport(handler)
    client = BifrostJudgeClient("http://bifrost:8080", "eval-judge-key")
    client._client = httpx.AsyncClient(transport=transport)

    messages = [{"role": "user", "content": "grade this"}]
    out = await client.judge(
        model="anthropic/claude-x", messages=messages, max_tokens=256
    )

    # Routed under the dedicated judge key (NOT a game identity).
    assert captured["auth"] == "Bearer eval-judge-key"
    assert captured["url"].endswith("/openai/chat/completions")
    # Fresh, stateless: the request body carries only the supplied messages.
    assert captured["body"]["messages"] == messages
    assert captured["body"]["model"] == "anthropic/claude-x"
    assert captured["body"]["max_tokens"] == 256
    assert json.loads(out) == {"ok": True}
    await client.aclose()


def test_move_prompt_truncates_large_state(caplog):
    big_state = {"cards": ["x" * 100 for _ in range(1000)]}  # well over the cap
    move = MoveInput(
        game_id="g1",
        target_seq=2,
        intended_action="play",
        reasoning="r",
        arguments={"card_id": "c2"},
        prior_state=big_state,
        resulting_state=big_state,
    )
    with caplog.at_level("INFO"):
        messages = build_move_messages(move, max_state_chars=500)
    user = messages[1]["content"]
    assert "[truncated" in user
    # The capped content is far smaller than the raw state JSON would be.
    assert len(user) < 5000
    assert any("Truncated" in rec.message for rec in caplog.records)


def test_move_prompt_no_truncation_under_cap():
    move = MoveInput(
        game_id="g1",
        target_seq=2,
        intended_action="play",
        reasoning="r",
        arguments={"card_id": "c2"},
        prior_state={"roundNumber": 1},
        resulting_state={"roundNumber": 1},
    )
    messages = build_move_messages(move, max_state_chars=10_000)
    assert "[truncated" not in messages[1]["content"]


def test_round_prompt_caps_move_count(caplog):
    moves = [
        MoveInput(
            game_id="g1",
            target_seq=s,
            intended_action="play",
            reasoning="r",
            arguments={},
            prior_state=None,
            resulting_state=None,
        )
        for s in range(50)
    ]
    rnd = RoundInput(
        game_id="g1",
        target_seq=49,
        from_seq=1,
        to_seq=49,
        round_number=1,
        moves=moves,
        closing_state={"roundNumber": 1},
    )
    with caplog.at_level("INFO"):
        messages = build_round_messages(rnd, max_round_moves=5)
    user = messages[1]["content"]
    assert "45 further moves omitted" in user
    assert any("Capped round move list" in rec.message for rec in caplog.records)


def test_flatten_content_handles_string_and_text_blocks():
    # Plain string passes through unchanged.
    assert BifrostJudgeClient._flatten_content("hello", joiner="\n") == "hello"
    # Typed text blocks are flattened; non-text blocks are ignored.
    blocks = [
        {"type": "text", "text": "a"},
        {"type": "image", "url": "x"},
        {"type": "text", "text": "b"},
    ]
    assert BifrostJudgeClient._flatten_content(blocks, joiner="\n") == "a\nb"
    assert BifrostJudgeClient._flatten_content(blocks, joiner="") == "ab"
    # Unknown shapes yield empty string.
    assert BifrostJudgeClient._flatten_content(42, joiner="\n") == ""


def test_extract_content_flattens_block_list():
    data = {"choices": [{"message": {"content": [{"type": "text", "text": "line"}]}}]}
    assert BifrostJudgeClient._extract_content(data) == "line"


@pytest.mark.asyncio
async def test_judge_raises_bifrost_error_on_gateway_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "down"}})

    transport = httpx.MockTransport(handler)
    client = BifrostJudgeClient("http://bifrost:8080", "k")
    client._client = httpx.AsyncClient(transport=transport)
    with pytest.raises(BifrostError) as excinfo:
        await client.judge(model="m", messages=[], max_tokens=1)
    assert excinfo.value.retryable is True
    await client.aclose()
