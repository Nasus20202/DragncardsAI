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
