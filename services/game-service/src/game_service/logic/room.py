"""DragnCards room event names and compatibility wrapper."""

from __future__ import annotations

from typing import Any, Callable

from game_service.logic.platform import DragnCardsPlatform


class PhoenixRoom(DragnCardsPlatform):
    """Source-compatible facade for the pre-platform-seam room constructor."""

    def __init__(self, client: Any, channel: Any) -> None:
        super().__init__(client=client, channel=channel)

    def register_state_handlers(
        self,
        on_full_state: Callable[[Any], None] | None = None,
        on_state_update: Callable[[Any], None] | None = None,
        on_bad_game_state: Callable[[Any], None] | None = None,
        on_state_unavailable: Callable[[Any], None] | None = None,
        on_alert: Callable[[Any], None] | None = None,
        on_gui_update: Callable[[Any], None] | None = None,
        on_terminal: Callable[[Any], None] | None = None,
    ) -> None:
        """Accept the legacy six-callback registration shape.

        ``on_terminal`` was added by the platform seam, but older callers still
        register the original six callbacks, often positionally.  A no-op is
        supplied for omitted callbacks so the channel never stores ``None`` as
        a handler while the new callback remains optional.
        """

        def noop(_payload: Any) -> None:
            return None

        super().register_state_handlers(
            on_full_state=on_full_state or noop,
            on_state_update=on_state_update or noop,
            on_bad_game_state=on_bad_game_state or noop,
            on_state_unavailable=on_state_unavailable or noop,
            on_alert=on_alert or noop,
            on_gui_update=on_gui_update or noop,
            on_terminal=on_terminal or noop,
        )


# The constants were part of the old module's import surface. Keep them as
# aliases while the implementation itself lives behind the platform seam.
CURRENT_STATE_EVENT = "current_state"
STATE_UPDATE_EVENT = "state_update"
BAD_GAME_STATE_EVENT = "bad_game_state"
STATE_UNAVAILABLE_EVENTS = (
    "unable_to_get_state_on_join",
    "unable_to_get_state_on_request",
)
ALERT_EVENT = "send_alert"
GUI_UPDATE_EVENT = "gui_update"

__all__ = [
    "PhoenixRoom",
    "CURRENT_STATE_EVENT",
    "STATE_UPDATE_EVENT",
    "BAD_GAME_STATE_EVENT",
    "STATE_UNAVAILABLE_EVENTS",
    "ALERT_EVENT",
    "GUI_UPDATE_EVENT",
]
