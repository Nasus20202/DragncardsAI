from __future__ import annotations

from pydantic import BaseModel


class ProviderResponse(BaseModel):
    provider_id: str
    model_prefix: str
    models: list[str]
    available: bool
    error: str | None = None


class SkillDefinitionResponse(BaseModel):
    name: str
    path: str
    content_markdown: str
