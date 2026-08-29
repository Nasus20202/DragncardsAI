from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from agent_orchestrator.integrations.bifrost import ModelReasoning
from agent_orchestrator.runtime.player_agents import REASONING_EFFORTS


def _effort_from_gateway_options(options: dict[str, Any]) -> str | None:
    reasoning = options.get("reasoning")
    if not isinstance(reasoning, dict):
        return None
    effort = reasoning.get("effort")
    return effort if isinstance(effort, str) else None


async def validate_reasoning_effort(
    bifrost_client: Any,
    *,
    provider_id: str | None,
    model_name: str | None,
    effort: str | None,
) -> None:
    """Validate one configured effort against the selected model's metadata.

    A missing model or unavailable metadata deliberately uses the legacy effort
    set. The rich Bifrost listing is advisory discovery data, so a temporary
    listing failure must not make existing low/medium/high configurations fail.
    """
    if effort is None:
        return
    if not provider_id or not model_name:
        allowed = REASONING_EFFORTS
    else:
        reasoning: ModelReasoning | None = None
        get_model_reasoning = getattr(bifrost_client, "get_model_reasoning", None)
        if get_model_reasoning is not None:
            try:
                reasoning = await get_model_reasoning(provider_id, model_name)
            except Exception:
                reasoning = None
        supported = reasoning.supported_efforts if reasoning is not None else None
        allowed = tuple(supported) if supported is not None else REASONING_EFFORTS

    if effort not in allowed:
        supported_text = ", ".join(allowed) if allowed else "none"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported reasoning effort {effort!r}; supported efforts: "
                f"{supported_text}"
            ),
        )


async def validate_gateway_reasoning(
    bifrost_client: Any,
    *,
    provider_id: str | None,
    model_name: str | None,
    gateway_options: dict[str, Any],
) -> None:
    await validate_reasoning_effort(
        bifrost_client,
        provider_id=provider_id,
        model_name=model_name,
        effort=_effort_from_gateway_options(gateway_options),
    )
