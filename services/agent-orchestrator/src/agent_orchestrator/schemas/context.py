from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from agent_orchestrator.schemas.base import StrictRequest


class CompactSessionRequest(StrictRequest):
    """Options for a manually triggered compaction.

    Compaction normally summarizes only the span since the previous checkpoint,
    on top of that checkpoint's summary. `from_session_start` ignores the
    checkpoint and re-reads the session's retained raw events instead, so a
    caller who believes an earlier summary lost something can rebuild it.
    Automatic compaction always uses the checkpointed form.
    """

    from_session_start: bool = False


class ContextTokenBreakdownResponse(BaseModel):
    system_prompt: int
    replay: int
    tools: int


class ContextMetadataResponse(BaseModel):
    tokens_used: int
    context_window_size: int
    usage_ratio: float
    compaction_count: int
    last_compacted_at: datetime | None
    multi_turn_memory: bool
    token_breakdown: ContextTokenBreakdownResponse
