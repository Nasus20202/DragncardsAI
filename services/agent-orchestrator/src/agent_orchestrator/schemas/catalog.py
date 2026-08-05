from __future__ import annotations

from pydantic import BaseModel


class ProviderResponse(BaseModel):
    provider_id: str
    model_prefix: str
    models: list[str]
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
