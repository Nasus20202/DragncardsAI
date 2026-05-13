from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from game_service.phoenix_client.client import Channel, PhoenixClient, PhxMessage

CURRENT_STATE_EVENT = "current_state"
STATE_UPDATE_EVENT = "state_update"
BAD_GAME_STATE_EVENT = "bad_game_state"
STATE_UNAVAILABLE_EVENTS = (
    "unable_to_get_state_on_join",
    "unable_to_get_state_on_request",
)
ALERT_EVENT = "send_alert"
GUI_UPDATE_EVENT = "gui_update"


@dataclass
class PhoenixRoom:
    client: PhoenixClient
    channel: Channel

    def register_state_handlers(
        self,
        *,
        on_full_state: Callable[[Any], None],
        on_state_update: Callable[[Any], None],
        on_bad_game_state: Callable[[Any], None],
        on_state_unavailable: Callable[[Any], None],
        on_alert: Callable[[Any], None],
        on_gui_update: Callable[[Any], None],
    ) -> None:
        self.channel.on(CURRENT_STATE_EVENT, on_full_state)
        self.channel.on(STATE_UPDATE_EVENT, on_state_update)
        self.channel.on(BAD_GAME_STATE_EVENT, on_bad_game_state)
        for event_name in STATE_UNAVAILABLE_EVENTS:
            self.channel.on(event_name, on_state_unavailable)
        self.channel.on(ALERT_EVENT, on_alert)
        self.channel.on(GUI_UPDATE_EVENT, on_gui_update)

    async def request_state(self, timeout: float) -> Any:
        await self.channel.push("request_state", {}, timeout=timeout)
        return await self.channel.wait_for_state_update(timeout=timeout)

    async def execute_game_action(
        self, payload: dict[str, Any], timeout: float
    ) -> None:
        await self.channel.push("game_action", payload, timeout=timeout)

    async def wait_for_state_change(self, timeout: float) -> None:
        await self.channel.wait_for_event(
            "state_update", "current_state", timeout=timeout
        )

    async def push_room_event(
        self, event: str, payload: dict[str, Any], timeout: float
    ) -> Any:
        return await self.channel.push(event, payload, timeout=timeout)

    async def send_room_event(self, event: str, payload: dict[str, Any]) -> None:
        msg = PhxMessage(
            join_ref=self.channel.join_ref,
            ref=self.client._next_ref(),
            topic=self.channel.topic,
            event=event,
            payload=payload,
        )
        await self.client._send(msg)

    async def set_seat(self, player_index: int, user_id: int) -> None:
        await self.send_room_event(
            "set_seat",
            {
                "player_i": player_index,
                "new_user_id": user_id,
                "timestamp": int(time.time() * 1000),
            },
        )

    async def set_spectator(self, user_id: int, spectating: bool) -> None:
        await self.send_room_event(
            "set_spectator",
            {"user_id": user_id, "value": spectating},
        )
