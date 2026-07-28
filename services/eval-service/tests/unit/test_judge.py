from __future__ import annotations

import json

import httpx
import pytest

from eval_service.integrations.bifrost import BifrostError, BifrostJudgeClient
from eval_service.judge.assembly import MoveInput, NeighbourMove, RoundInput
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
    """The judge sends only the prompt, pinned to the named judge key."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["key_name"] = request.headers.get("x-bf-api-key")
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"ok": True})}}]},
        )

    transport = httpx.MockTransport(handler)
    client = BifrostJudgeClient(
        "http://bifrost:8080", "gateway-token", key_name="eval-judge"
    )
    client._client = httpx.AsyncClient(transport=transport)

    messages = [{"role": "user", "content": "grade this"}]
    out = await client.judge(
        model="anthropic/claude-x", messages=messages, max_tokens=256
    )

    assert captured["auth"] == "Bearer gateway-token"
    # The named-key header is what pins the call to the dedicated judge key: the
    # bearer above does NOT select a provider key.
    assert captured["key_name"] == "eval-judge"
    assert captured["url"].endswith("/openai/chat/completions")
    # Fresh, stateless: the request body carries only the supplied messages.
    assert captured["body"]["messages"] == messages
    assert captured["body"]["model"] == "anthropic/claude-x"
    assert captured["body"]["max_tokens"] == 256
    assert json.loads(out) == {"ok": True}
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "model", ["openrouter/anthropic/claude-sonnet-4", "gemini/gemini-2.5-pro"]
)
async def test_judge_key_selection_is_provider_agnostic(model):
    """The same judge key name is selected whatever provider the model routes to.

    Bifrost resolves ``x-bf-api-key`` against the TARGET provider's keys, so one
    header pins the judge identity for every provider that defines that key.
    """
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["key_name"] = request.headers.get("x-bf-api-key")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = BifrostJudgeClient("http://bifrost:8080", "t", key_name="eval-judge")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await client.judge(model=model, messages=[], max_tokens=8)
    assert captured["key_name"] == "eval-judge"
    await client.aclose()


@pytest.mark.asyncio
async def test_judge_omits_key_header_when_selection_disabled():
    """An empty key name opts out: no header, so the normal key pool applies."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = BifrostJudgeClient("http://bifrost:8080", "t", key_name="")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await client.judge(model="anthropic/claude-x", messages=[], max_tokens=8)
    assert "x-bf-api-key" not in captured["headers"]
    await client.aclose()


@pytest.mark.asyncio
async def test_missing_judge_key_is_a_definitive_non_retryable_error():
    """Bifrost's "no supported key found" 400 must fail fast, not be retried.

    This is the real-gateway response when the target provider has no key of the
    judge's name (or its env reference is unset) -- the guarantee that judge
    traffic can never silently fall back to a game-playing key.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": 'no supported key found with name "eval-judge" '
                    "for provider: openrouter and model: x"
                }
            },
        )

    client = BifrostJudgeClient("http://bifrost:8080", "t", key_name="eval-judge")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(BifrostError) as excinfo:
        await client.judge(model="openrouter/x", messages=[], max_tokens=8)
    assert excinfo.value.retryable is False
    assert 'no supported key found with name "eval-judge"' in str(excinfo.value)
    await client.aclose()


@pytest.mark.asyncio
async def test_named_key_providers_lists_providers_with_the_judge_key():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/keys"
        return httpx.Response(
            200,
            json=[
                {"name": "openai-primary", "provider": "openai"},
                {"name": "eval-judge", "provider": "openai"},
                {"name": "eval-judge", "provider": "openrouter"},
                {"name": "anthropic-primary", "provider": "anthropic"},
                "not-a-dict",
            ],
        )

    client = BifrostJudgeClient("http://bifrost:8080", "t", key_name="eval-judge")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await client.named_key_providers("eval-judge") == frozenset(
        {"openai", "openrouter"}
    )
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, text="admin auth required"),
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"keys": []}),
    ],
)
async def test_named_key_providers_returns_none_when_unreadable(response):
    # "Cannot tell" must be distinguishable from "no judge keys configured".
    client = BifrostJudgeClient("http://bifrost:8080", "t", key_name="eval-judge")
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: response)
    )
    assert await client.named_key_providers("eval-judge") is None
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


def _windowed_move() -> MoveInput:
    """The reporter's case: `exhaust_card` then `modify_tokens` inside one round."""
    return MoveInput(
        game_id="g1",
        target_seq=10,
        intended_action="modify_tokens",
        reasoning="assign the damage",
        arguments={"amount": 3},
        prior_state=None,
        resulting_state=None,
        context_before=[
            NeighbourMove(
                seq=8,
                intended_action="exhaust_card",
                arguments={"instance_id": "hero"},
                reasoning="attack with the hero",
            )
        ],
        context_after=[
            NeighbourMove(
                seq=12,
                intended_action="next_step",
                arguments={},
                reasoning="x" * 900,
            )
        ],
        # Already the round OF PLAY, as detect_round_boundaries reports it.
        round_number=1,
        round_span=(5, 14),
    )


def test_move_prompt_renders_the_round_window_with_hindsight_labelled():
    user = build_move_messages(_windowed_move(), max_context_reasoning_chars=100)[1][
        "content"
    ]
    assert "EARLIER IN THIS ROUND" in user
    assert 'seq 8: action="exhaust_card"' in user
    assert "LATER IN THIS ROUND" in user
    assert "do not judge the decision on hindsight" in user
    # A verbose neighbour cannot bloat the prompt.
    assert "[+" in user
    assert len(user) < 3000


def test_move_prompt_names_the_round_of_play_and_its_span():
    # The prompt must name the round of PLAY. Showing a judge DragnCards' raw
    # counter -- 0 throughout the first round -- would misstate the position.
    user = build_move_messages(_windowed_move())[1]["content"]
    assert "in Round 1 (seqs 5-14)" in user
    assert "Round 0" not in user


def test_move_prompt_tells_the_judge_a_play_spans_several_actions():
    # Without this instruction a judge asked "was this a strong strategic choice"
    # about `exhaust_card` alone answers no, which is the reported defect.
    system = build_move_messages(_windowed_move())[0]["content"]
    assert "SEVERAL recorded actions" in system
    assert "STEP IT IS within the play" in system
    assert "do NOT score it down for being incomplete" in system
    assert "charge the same play against every action" in system


def test_move_prompt_omits_the_window_blocks_when_empty():
    move = MoveInput(
        game_id="g1",
        target_seq=10,
        intended_action="move_card",
        reasoning="r",
        arguments={},
        prior_state=None,
        resulting_state=None,
    )
    user = build_move_messages(move)[1]["content"]
    assert "EARLIER IN THIS ROUND" not in user
    assert "LATER IN THIS ROUND" not in user
    # No detected round -> no round claim in the prompt either.
    assert "in Round" not in user


def test_move_prompt_projects_a_raw_recorded_state():
    # The recorded state is the raw DragnCards room state; the prompt must carry
    # the board rather than the internal delta log that dominates it.
    raw = {
        "deltas": [{"noise": "n" * 2000}],
        "game": {
            "roundNumber": 4,
            "cardById": {
                "rhino_1": {
                    "groupId": "sharedVillain",
                    "stackId": "rhino_1",
                    "currentSide": "A",
                    "tokens": {"damage": 5},
                    "sides": {"A": {"name": "Rhino", "type": "Villain"}},
                }
            },
        },
    }
    move = MoveInput(
        game_id="g1",
        target_seq=2,
        intended_action="modify_tokens",
        reasoning="r",
        arguments={},
        prior_state=raw,
        resulting_state=raw,
    )
    user = build_move_messages(move, max_state_chars=20_000)[1]["content"]
    assert "Rhino" in user
    assert "deltas" not in user
    assert "[truncated" not in user


def test_round_prompt_states_how_many_non_strategic_moves_were_omitted():
    rnd = RoundInput(
        game_id="g1",
        target_seq=9,
        from_seq=1,
        to_seq=9,
        round_number=1,
        moves=[],
        closing_state=None,
        omitted_non_strategic=4,
    )
    user = build_round_messages(rnd)[1]["content"]
    assert "4 non-strategic action(s) omitted" in user
