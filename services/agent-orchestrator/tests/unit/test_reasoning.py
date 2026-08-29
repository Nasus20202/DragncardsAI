from __future__ import annotations

import pytest
from fastapi import HTTPException

from agent_orchestrator.api.reasoning import validate_gateway_reasoning
from agent_orchestrator.integrations.bifrost import ModelReasoning


class _Bifrost:
    def __init__(self, supported_efforts: list[str] | None):
        self.supported_efforts = supported_efforts

    async def get_model_reasoning(
        self, provider_id: str, model_name: str
    ) -> ModelReasoning:
        return ModelReasoning(supported_efforts=self.supported_efforts)


@pytest.mark.asyncio
async def test_gateway_reasoning_accepts_advertised_effort():
    await validate_gateway_reasoning(
        _Bifrost(["minimal"]),
        provider_id="openrouter",
        model_name="gemma",
        gateway_options={"reasoning": {"effort": "minimal"}},
    )


@pytest.mark.asyncio
async def test_gateway_reasoning_rejects_explicitly_unsupported_effort():
    with pytest.raises(HTTPException) as exc_info:
        await validate_gateway_reasoning(
            _Bifrost([]),
            provider_id="openrouter",
            model_name="gemma",
            gateway_options={"reasoning": {"effort": "high"}},
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "gateway_options",
    [
        {"reasoning": []},
        {"reasoning": {"effort": 3}},
        {"reasoning": {"effort": ""}},
    ],
)
async def test_gateway_reasoning_rejects_malformed_raw_options(gateway_options):
    with pytest.raises(HTTPException) as exc_info:
        await validate_gateway_reasoning(
            _Bifrost(None),
            provider_id="openrouter",
            model_name="gemma",
            gateway_options=gateway_options,
        )

    assert exc_info.value.status_code == 400
