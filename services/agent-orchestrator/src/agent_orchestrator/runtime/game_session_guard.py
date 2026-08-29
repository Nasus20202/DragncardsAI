"""Server-side binding of game-service calls to an agent session.

Every agent session may discover one game-service session on its first successful
call. Once ``metadata.game_id`` is present, a model-supplied ``session_id`` is
only authorized when it names that same game. The check is deliberately pure and
runs before any game-service request, so a rejected identifier cannot cause the
downstream service to return another game's state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_EXISTING_GAME_RESOLVER_TOOLS = frozenset({"attach_game", "lookup_session_by_slug"})


@dataclass(frozen=True)
class GameSessionBindingViolation:
    """A game-service call targeted a different session than the caller's binding.

    The violation intentionally does not retain either identifier. Neither the
    model-facing refusal nor a durable event needs to echo a target id, and
    omitting both keeps this boundary from disclosing details about another game.
    """

    tool_name: str

    @property
    def message(self) -> str:
        """Return a correction that does not reveal the requested game's state."""
        return (
            f"Refused: `{self.tool_name}` may only target this agent session's "
            "bound game. Use the bound game's session_id and do not target a "
            "different game."
        )


def check_game_session_binding(
    *,
    assignment: str | None,
    tool_name: str,
    arguments: dict[str, Any],
    bound_game_id: str | None,
) -> GameSessionBindingViolation | None:
    """Return a violation when a bound session names another game.

    An unbound session is allowed to make its first game-service call. The
    existing result/argument capture path then records that game's id, preserving
    first-call discovery. Calls that enumerate or resolve existing game
    instances are refused once a session is bound because their arguments do not
    carry a comparable canonical game id.
    """
    if assignment != "game-service" or not bound_game_id:
        return None
    if not isinstance(arguments, dict):
        return None
    if tool_name in _EXISTING_GAME_RESOLVER_TOOLS or tool_name == "list_games":
        return GameSessionBindingViolation(tool_name=tool_name)
    requested_game_id = arguments.get("session_id")
    if not isinstance(requested_game_id, str) or not requested_game_id:
        return None
    if requested_game_id == bound_game_id:
        return None
    return GameSessionBindingViolation(tool_name=tool_name)
