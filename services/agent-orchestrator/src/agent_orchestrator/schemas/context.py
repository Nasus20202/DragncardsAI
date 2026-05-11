from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ContextMetadataResponse(BaseModel):
    tokens_used: int
    context_window_size: int
    usage_ratio: float
    compaction_count: int
    last_compacted_at: datetime | None
    multi_turn_memory: bool
