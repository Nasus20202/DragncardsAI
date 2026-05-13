"""Compatibility wrappers for transcript construction.

The session transcript module now owns replay selection and reconstruction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent_orchestrator.runtime.session_transcript import (
    SessionTranscriptService,
    build_message_history,
    reconstruct_job_messages as _reconstruct_job_messages,
)

if TYPE_CHECKING:
    from agent_orchestrator.storage.repository import Repository

__all__ = [
    "SessionTranscriptService",
    "build_message_history",
    "_reconstruct_job_messages",
]
