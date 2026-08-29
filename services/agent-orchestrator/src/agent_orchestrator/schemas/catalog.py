from __future__ import annotations

from pydantic import BaseModel, Field


class ModelReasoningResponse(BaseModel):
    mandatory: bool | None = None
    default_enabled: bool | None = None
    supported_efforts: list[str] | None = None
    default_effort: str | None = None


class ModelCapabilitiesResponse(BaseModel):
    reasoning: ModelReasoningResponse | None = None


class ProviderResponse(BaseModel):
    provider_id: str
    model_prefix: str
    models: list[str]
    model_capabilities: dict[str, ModelCapabilitiesResponse] = Field(default_factory=dict)
    available: bool
    error: str | None = None


class ProviderCacheRefreshResponse(BaseModel):
    status: str
    providers: int
    keys_cleared: int


class SkillDefinitionResponse(BaseModel):
    name: str
    path: str
    description: str = ""
    metadata: dict[str, str] = {}
    # The skill's markdown reference files, by path relative to the skill
    # directory -- exactly the names `load_skill_reference` accepts, so a
    # consumer can offer a listed entry and have the selection resolve. Always
    # present (empty for a skill with none) so nobody has to tell "no references"
    # apart from "not reported".
    references: list[str] = []
