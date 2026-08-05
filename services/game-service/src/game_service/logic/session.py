"""
GameSession dataclass.

Represents a single active DragnCards game room with:
- A persistent WebSocket connection (PhoenixClient + Channel)
- Cached latest game state (updated on broadcasts)
- Metadata: session ID, plugin name, creation time, room slug
- Inbound event buffers: alerts (deque, maxlen=50), GUI updates (dict per player)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable

from game_service.coordination.history_emitter import (
    HistoryEmitter,
    NullHistoryEmitter,
)
from game_service.logic.actions import (
    GameAction,
    RawAction,
    SetPlayerCountAction,
    translate_action,
)
from game_service.logic.exceptions import (
    BadGameStateError,
    SessionError,
    SnapshotValidationError,
    StateUnavailableError,
)
from game_service.logic.room import PhoenixRoom
from game_service.logic.seats import (
    SEAT_IDS,
    normalise_seat_id,
    seat_held_by,
)
from game_service.logic.snapshots import GameStateSnapshot, SNAPSHOT_SCHEMA_VERSION
from game_service.phoenix_client.client import (
    Channel,
    PhoenixChannelError,
    PhoenixClient,
)
from game_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _extract_alert_text(alert: dict) -> str | None:
    """Extract error text from an alert dict."""
    if alert.get("level") == "error":
        return alert.get("text", str(alert))
    if "error" in alert:
        return str(alert.get("error"))
    return None


@dataclass
class GameSession:
    """Represents a single active game session."""

    session_id: str
    plugin_name: str
    plugin_id: int
    room_slug: str
    created_at: datetime
    client: PhoenixClient
    channel: Channel
    initial_state: Any = None
    on_close: Callable[[], Awaitable[None]] | None = None
    history_emitter: HistoryEmitter | None = None
    # Non-emitting, server-reaped reconstruction session (view-only). When true
    # this session never emits history events and is eligible for TTL reaping.
    ephemeral: bool = False
    room: PhoenixRoom = field(init=False)
    _state: Any = field(default=None, init=False)
    _state_stale: bool = field(default=False, init=False)
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _bad_state: bool = field(default=False, init=False)
    _state_unavailable: bool = field(default=False, init=False)
    _alerts: deque = field(default_factory=lambda: deque(maxlen=50), init=False)
    _gui_updates: dict = field(default_factory=dict, init=False)
    _action_error: str | None = field(default=None, init=False)

    def __post_init__(self):
        if self.history_emitter is None:
            self.history_emitter = NullHistoryEmitter()
        self.room = PhoenixRoom(client=self.client, channel=self.channel)
        self.room.register_state_handlers(
            on_full_state=self._on_full_state,
            on_state_update=self._on_delta,
            on_bad_game_state=self._on_bad_game_state,
            on_state_unavailable=self._on_state_unavailable,
            on_alert=self._on_alert,
            on_gui_update=self._on_gui_update,
        )
        self._state = self.initial_state

    def _on_full_state(self, payload: Any) -> None:
        self._state = payload

    def _on_delta(self, payload: Any) -> None:
        self._state_stale = True

    def _on_bad_game_state(self, payload: Any) -> None:
        logger.warning(
            "bad_game_state received for session %s: %s", self.session_id, payload
        )
        self._bad_state = True

    def _on_state_unavailable(self, payload: Any) -> None:
        logger.warning(
            "unable_to_get_state received for session %s: %s", self.session_id, payload
        )
        self._state_unavailable = True

    def _on_alert(self, payload: Any) -> None:
        self._alerts.append(payload)
        if isinstance(payload, dict):
            text = _extract_alert_text(payload)
            if text:
                self._action_error = text

    def _on_gui_update(self, payload: Any) -> None:
        player_n = payload.get("player_n") if isinstance(payload, dict) else None
        if player_n:
            self._gui_updates[player_n] = payload

    def _check_state_flags(self) -> None:
        if self._bad_state:
            raise BadGameStateError(
                f"Session {self.session_id}: game state is corrupted or unavailable"
            )
        if self._state_unavailable:
            raise StateUnavailableError(
                f"Session {self.session_id}: game state is temporarily unavailable"
            )

    async def _request_fresh_state(self, timeout: float) -> Any:
        with tracer.start_as_current_span("game_session.request_state"):
            new_state = await self.room.request_state(timeout=timeout)
            self._check_state_flags()
            async with self._state_lock:
                self._state = new_state
                self._state_stale = False
            return new_state

    async def get_state(self) -> Any:
        with tracer.start_as_current_span("game_session.get_state"):
            self._check_state_flags()
            async with self._state_lock:
                if self._state is not None and not self._state_stale:
                    return self._state

                stale = self._state_stale

            logger.info(
                "get_state: session_id=%s fetching fresh state (stale=%s)",
                self.session_id,
                stale,
            )
            try:
                await self._request_fresh_state(timeout=10.0)
            except (PhoenixChannelError, asyncio.TimeoutError) as exc:
                logger.error(
                    "get_state: session_id=%s failed: %s", self.session_id, exc
                )
                raise SessionError(f"Could not fetch game state: {exc}") from exc

            self._check_state_flags()
            async with self._state_lock:
                return self._state

    async def execute_action(self, action: GameAction, timeout: float = 15.0) -> Any:
        action_name = type(action).__name__
        with tracer.start_as_current_span(
            "game_session.execute_action",
            attributes={"game.action.name": action_name},
        ):
            self._check_state_flags()
            # Clear any previous action error before executing
            self._action_error = None
            payload = translate_action(action)
            logger.info(
                "execute_action: session_id=%s payload=%r", self.session_id, payload
            )
            try:
                await self.room.execute_game_action(payload, timeout=timeout)
                await self.room.wait_for_state_change(timeout=timeout)
                self._check_state_flags()
                new_state = await self._request_fresh_state(timeout=timeout)
                # Check for action errors in game messages
                self._check_action_messages(new_state)
                logger.info(
                    "execute_action: session_id=%s -> state updated", self.session_id
                )
                await self._emit_history_state_event(new_state, action=action)
                return new_state
            except PhoenixChannelError as exc:
                logger.error(
                    "execute_action: session_id=%s rejected: %s", self.session_id, exc
                )
                raise SessionError(f"Action rejected by DragnCards: {exc}") from exc
            except asyncio.TimeoutError as exc:
                logger.warning(
                    "execute_action: session_id=%s timed out, attempting state refresh",
                    self.session_id,
                )
                try:
                    recovery_timeout = min(timeout, 5.0)
                    new_state = await self._request_fresh_state(
                        timeout=recovery_timeout
                    )
                    self._check_action_messages(new_state)
                    logger.info(
                        "execute_action: session_id=%s recovered via request_state",
                        self.session_id,
                    )
                    await self._emit_history_state_event(new_state, action=action)
                    return new_state
                except (PhoenixChannelError, asyncio.TimeoutError) as recovery_exc:
                    logger.error(
                        "execute_action: session_id=%s recovery failed: %s",
                        self.session_id,
                        recovery_exc,
                    )
                raise SessionError(
                    "Timed out waiting for state update after action"
                ) from exc

    def _check_action_messages(self, state: Any) -> None:
        """Check game messages for action errors and populate _action_error if found."""
        if not isinstance(state, dict):
            return
        game = state.get("game")
        if not isinstance(game, dict):
            return
        messages = game.get("messages")
        if not isinstance(messages, list):
            return
        for message in reversed(messages):
            if not isinstance(message, str):
                continue
            if "ABORT:" in message or "Error in Marvel Champions triggered" in message:
                self._action_error = message
                break

    async def _emit_history_state_event(
        self, state: Any, *, action: GameAction | None = None
    ) -> None:
        """Best-effort publish of the post-action state to the history bus.

        Emits exactly one event per successfully executed action with a durable,
        monotonically increasing ``producer_offset`` sourced from the shared
        history Valkey (so it survives session restore / service restart and
        never regenerates a previously used idempotency key). The executed
        action is serialized into a replayable form (the body accepted by
        ``POST /games/{id}/actions``) and carried in the envelope so the
        history-service can replay it forward during restore.

        Emission is skipped entirely when the action failed/was aborted in-game
        (so a rejected action never advances the offset or records a move) and
        when the durable offset cannot be allocated (so we never fabricate a
        non-durable offset that would collide later). Never raises and never
        alters the action result returned to the caller: any failure is logged
        and swallowed so emission cannot break action execution.
        """
        emitter = self.history_emitter
        if emitter is None:
            return
        # Ephemeral reconstruction sessions are view-only: they must never reach
        # the history bus (no game_state/agent_move/any events) so they never
        # appear in the games list and produce nothing to clean up.
        if self.ephemeral:
            return
        # Do not record (or advance the offset for) a rejected/aborted action.
        if self._action_error is not None:
            return
        try:
            producer_offset = await emitter.next_producer_offset(self.session_id)
        except Exception as exc:  # best-effort: never break the action
            logger.warning(
                "execute_action: session_id=%s history offset failed: %s",
                self.session_id,
                exc,
            )
            return
        if producer_offset is None:
            # No durable offset available; skip rather than risk a collision.
            return
        action_args: dict[str, Any] | None = None
        if action is not None:
            try:
                action_args = action.model_dump(mode="json")
            except Exception:  # pragma: no cover - defensive
                action_args = None
        try:
            await emitter.emit_state_event(
                game_id=self.session_id,
                producer_offset=producer_offset,
                state=state,
                action_args=action_args,
                plugin_name=self.plugin_name,
            )
        except Exception as exc:  # best-effort: never break the action
            logger.warning(
                "execute_action: session_id=%s history emit failed: %s",
                self.session_id,
                exc,
            )

    async def load_prebuilt_deck(
        self,
        deck_id: str,
        timeout: float = 15.0,
        player_n: str = SEAT_IDS[0],
    ) -> Any:
        """Load a prebuilt deck on behalf of ``player_n``.

        The seat is load-bearing, not a label. A Marvel Champions hero deck
        declares its cards against the templated groups ``playerNDeck`` and
        ``playerNNemesisSet``, and DragnCards substitutes the ``N`` from
        ``$PLAYER_N`` — which comes from the ``player_ui`` this action carries.
        Loading with the wrong seat puts that hero's cards in another seat's
        groups rather than merely mislabelling the load.
        """
        player_n = normalise_seat_id(player_n)
        # Clear any previous action error before executing (mirrors execute_action).
        self._action_error = None
        load_action = RawAction(
            action_list=["LOAD_CARDS", deck_id],
            description=f"Loaded prebuilt deck {deck_id}",
            player_n=player_n,
        )
        payload = translate_action(load_action)
        try:
            await self.room.execute_game_action(payload, timeout=timeout)
            await self.room.wait_for_state_change(timeout=timeout)
            self._check_state_flags()
            new_state = await self._request_fresh_state(timeout=timeout)
            self._check_action_messages(new_state)
            # Snapshot the post-load board so the recorded timeline never gaps
            # over a whole-deck deal. Best-effort: never breaks the deck load.
            await self._emit_history_state_event(new_state, action=load_action)
            return new_state
        except PhoenixChannelError as exc:
            raise SessionError(f"load_prebuilt_deck rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError(
                "Timed out waiting for state after load_prebuilt_deck"
            ) from exc

    async def export_state(self) -> GameStateSnapshot:
        state = await self.get_state()
        if not isinstance(state, dict) or not isinstance(state.get("game"), dict):
            raise SessionError(
                f"Session {self.session_id}: current state has no exportable game payload"
            )
        return GameStateSnapshot(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            plugin_name=self.plugin_name,
            game=state["game"],
        )

    async def load_state(
        self, snapshot: GameStateSnapshot | dict[str, Any], timeout: float = 15.0
    ) -> Any:
        snapshot_doc = (
            snapshot
            if isinstance(snapshot, GameStateSnapshot)
            else GameStateSnapshot.model_validate(snapshot)
        )
        if snapshot_doc.schema_version != SNAPSHOT_SCHEMA_VERSION:
            raise SnapshotValidationError(
                f"Unsupported snapshot schema version {snapshot_doc.schema_version}; expected {SNAPSHOT_SCHEMA_VERSION}"
            )
        if snapshot_doc.plugin_name != self.plugin_name:
            raise SnapshotValidationError(
                f"Snapshot plugin {snapshot_doc.plugin_name!r} does not match session plugin {self.plugin_name!r}"
            )

        # Clear any previous action error before executing (mirrors execute_action).
        self._action_error = None
        payload = {
            "action": "set_game",
            "options": {
                "game": snapshot_doc.game,
                "description": "Load game state snapshot",
            },
            "timestamp": int(time.time() * 1000),
        }
        try:
            await self.room.execute_game_action(payload, timeout=timeout)
            await self.room.wait_for_state_change(timeout=timeout)
            self._check_state_flags()
            new_state = await self._request_fresh_state(timeout=timeout)
            self._check_action_messages(new_state)
            # Snapshot the replaced board so the recorded timeline reflects the
            # loaded state. No replayable action accompanies a raw state load.
            # Best-effort: never breaks the load.
            await self._emit_history_state_event(new_state)
            return new_state
        except PhoenixChannelError as exc:
            raise SessionError(f"load_state rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for state after load_state") from exc

    async def reset_game(
        self, save: bool = False, reload_plugin: bool = False, timeout: float = 15.0
    ) -> Any:
        event = "reset_and_reload" if reload_plugin else "reset_game"
        logger.info(
            "reset_game: session_id=%s event=%s save=%s", self.session_id, event, save
        )
        # Clear any previous action error before executing (mirrors execute_action).
        self._action_error = None
        try:
            await self.room.push_room_event(
                event, {"options": {"save?": save}}, timeout=timeout
            )
            new_state = await self._request_fresh_state(timeout=timeout)
            self._bad_state = False
            self._check_action_messages(new_state)
            # Snapshot the reset board so the recorded timeline captures the
            # reset. No replayable action accompanies a room-level reset.
            # Best-effort: never breaks the reset.
            await self._emit_history_state_event(new_state)
            logger.info("reset_game: session_id=%s -> state updated", self.session_id)
            return new_state
        except PhoenixChannelError as exc:
            logger.error("reset_game: session_id=%s rejected: %s", self.session_id, exc)
            raise SessionError(f"reset_game rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            logger.error("reset_game: session_id=%s timed out", self.session_id)
            raise SessionError("Timed out waiting for state after reset") from exc

    async def set_seat(self, player_id: str, user_id: int) -> None:
        """Push a seat assignment without waiting to see whether it took.

        ``player_id`` is a DragnCards seat id (``player1``..``player4``) because
        upstream uses this value directly as a key of the room's seat map.

        Prefer :meth:`claim_seat` when the answer matters: this method cannot
        report failure, since the ``set_seat`` channel event is written to the
        socket without a reply being awaited.
        """
        await self.room.set_seat(
            player_id=normalise_seat_id(player_id), user_id=user_id
        )

    async def claim_seat(
        self,
        player_id: str,
        user_id: int,
        timeout: float = 5.0,
        poll_interval: float = 0.25,
    ) -> None:
        """Seat ``user_id`` at ``player_id`` and confirm it from room state.

        The ``set_seat`` event carries no usable acknowledgement — the upstream
        handler swallows a failed sit-down into an error flag on the game — so
        the room's own state is the only authority on whether a seat was taken.
        Raises :class:`SessionError` if the seat has not taken within ``timeout``.
        """
        player_id = normalise_seat_id(player_id)
        with tracer.start_as_current_span(
            "game_session.claim_seat",
            attributes={"game.seat.id": player_id},
        ):
            await self.set_seat(player_id=player_id, user_id=user_id)

            deadline = time.monotonic() + timeout
            while True:
                # Occupancy changes arrive as a broadcast, so the cached state is
                # not necessarily the state that reflects the push.
                try:
                    state = await self._request_fresh_state(timeout=timeout)
                except (PhoenixChannelError, asyncio.TimeoutError) as exc:
                    # A room that will not answer cannot confirm a seat. Report
                    # it as a failed claim rather than letting a transport error
                    # surface as an unhandled fault.
                    raise SessionError(
                        f"Could not confirm seat {player_id}: {exc}"
                    ) from exc
                if seat_held_by(state, player_id, user_id):
                    logger.info(
                        "claim_seat: session_id=%s seat=%s user_id=%s claimed",
                        self.session_id,
                        player_id,
                        user_id,
                    )
                    return
                if time.monotonic() >= deadline:
                    break
                await asyncio.sleep(poll_interval)

            raise SessionError(
                f"Seat {player_id} did not become held by user {user_id} "
                f"within {timeout}s"
            )

    async def set_spectator(self, user_id: int, spectating: bool) -> None:
        await self.room.set_spectator(user_id=user_id, spectating=spectating)

    async def set_player_count(
        self,
        num_players: int,
        layout_id: str | None = None,
        timeout: float = 15.0,
    ) -> Any:
        logger.info(
            "set_player_count: session_id=%s num_players=%s layout_id=%r",
            self.session_id,
            num_players,
            layout_id,
        )
        return await self.execute_action(
            SetPlayerCountAction(num_players=num_players, layout_id=layout_id),
            timeout=timeout,
        )

    async def close_room(self, timeout: float = 10.0) -> None:
        try:
            await self.room.push_room_event("close_room", {"options": {}}, timeout)
        except PhoenixChannelError as exc:
            raise SessionError(f"close_room rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for close_room ack") from exc
        finally:
            if self.on_close is not None:
                try:
                    await self.on_close()
                except Exception:
                    pass

    async def send_alert(self, message: str, timeout: float = 10.0) -> None:
        try:
            await self.room.push_room_event("send_alert", {"message": message}, timeout)
        except PhoenixChannelError as exc:
            raise SessionError(f"send_alert rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for send_alert ack") from exc

    async def save_replay(self, timeout: float = 10.0) -> None:
        timestamp = int(time.time() * 1000)
        try:
            await self.room.push_room_event(
                "save_replay", {"options": {}, "timestamp": timestamp}, timeout
            )
        except PhoenixChannelError as exc:
            raise SessionError(f"save_replay rejected: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise SessionError("Timed out waiting for save_replay ack") from exc

    def get_alerts(self) -> list[dict]:
        return list(self._alerts)

    def get_action_error(self) -> str | None:
        """Return the error from the most recent action execution, if any."""
        return self._action_error

    def get_gui_updates(self) -> dict[str, Any]:
        return dict(self._gui_updates)

    def to_metadata(self) -> dict:
        return {
            "session_id": self.session_id,
            "plugin_name": self.plugin_name,
            "plugin_id": self.plugin_id,
            "room_slug": self.room_slug,
            "created_at": self.created_at.isoformat(),
            "frontend_url": None,
            "ephemeral": self.ephemeral,
        }
