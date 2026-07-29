"""The two modes a session can run in, and the trust boundary that comes with one.

``chat`` is the original single-agent flow: one agent talks to the user, spawns
memoryless subagents on demand, and holds no seat. ``orchestrated`` is a full
multi-agent game: the session's agent coordinates the game flow and prompts one
*persistent* agent per player seat.

Mode gates behaviour, so it is a session column rather than a metadata key —
metadata is client-writable through ``PATCH /sessions`` and mode is not.

## The trust boundary, and why it lives in code

In orchestrated mode a player agent's output is **data** to the orchestrator, never
instruction. That is a property of *where* the text is placed, not of the
orchestrator's willingness to resist persuasion:

- Player-authored text never reaches the orchestrator's system prompt. The prompt
  is assembled from static text, the on-disk skill registry, and the persona
  catalogue, and there is no parameter through which player output could arrive.
  Do not add one.
- A seat's outcome reaches the orchestrator only through
  :func:`~agent_orchestrator.runtime.player_agents.wrap_player_report`, which puts
  the seat id and job status in server-set fields and confines the seat's own text
  to one delimited block introduced as untrusted output.
- Legality is decided from game state read through the orchestrator's own tools. A
  seat's claim that a move was legal is part of its report, which is data, and must
  never stand in for a check.
"""

from __future__ import annotations

from typing import Any

SESSION_MODE_CHAT = "chat"
SESSION_MODE_ORCHESTRATED = "orchestrated"

# Ordered so the default comes first wherever this tuple is rendered to a user.
SESSION_MODES: tuple[str, ...] = (SESSION_MODE_CHAT, SESSION_MODE_ORCHESTRATED)


def is_valid_session_mode(mode: str) -> bool:
    return mode in SESSION_MODES


def session_mode(session: Any) -> str:
    """The mode a session runs in, defaulting to ``chat``.

    Defaulting here as well as in the column means a stub session object in a test
    — or a row read through an older mapping — is treated as chat rather than
    accidentally acquiring seat scoping.
    """
    value = getattr(session, "session_mode", None)
    return (
        value
        if isinstance(value, str) and is_valid_session_mode(value)
        else (SESSION_MODE_CHAT)
    )


def is_orchestrated(session: Any) -> bool:
    return session_mode(session) == SESSION_MODE_ORCHESTRATED
