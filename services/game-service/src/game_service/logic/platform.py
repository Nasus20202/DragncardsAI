"""Platform drivers used by :mod:`game_service.logic.session`.

The game service owns the session and HTTP surfaces, while a platform driver owns
the transport details of a particular playtable.  The first implementation is
DragnCards; keeping the contract here makes adding another transport possible
without teaching ``GameSession`` about its wire protocol.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol, runtime_checkable

from game_service.dragncards.auth_cache import DragnCardsAuthCache, DragnCardsIdentity
from game_service.dragncards.http_client import create_room
from game_service.logic.exceptions import (
    BadGameStateError,
    EnumeratedOptionError,
    PlatformTransportError,
    PlatformTimeoutError,
    SessionError,
)
from game_service.phoenix_client.client import (
    Channel,
    PhoenixChannelError,
    PhoenixClient,
    PhxMessage,
)

PlatformSlug = Literal["dragncards", "marvel-lcg"]
MoveSurface = Literal["typed_actions", "enumerated_options"]
PlatformRegistry = dict[PlatformSlug, "GamePlatform"]
DRAGNCARDS_PLATFORM: PlatformSlug = "dragncards"
MARVEL_LCG_PLATFORM: PlatformSlug = "marvel-lcg"
PLATFORM_SLUGS: tuple[PlatformSlug, ...] = (
    DRAGNCARDS_PLATFORM,
    MARVEL_LCG_PLATFORM,
)


@dataclass(frozen=True)
class HeroDeckSelection:
    """A neutral seat and the opaque hero-deck id selected for it."""

    seat: str
    hero_deck_id: str


@dataclass(frozen=True)
class DragnCardsCreateSpec:
    """Typed creation input owned by the DragnCards platform."""

    platform: Literal["dragncards"]
    plugin_name: str
    plugin_info: dict[str, Any]


@dataclass(frozen=True)
class MarvelLcgCreateSpec:
    """Typed creation input owned by the marvel-lcg platform."""

    platform: Literal["marvel-lcg"]
    scenario_id: str
    hero_decks: tuple[HeroDeckSelection, ...]


PlatformCreateSpec = DragnCardsCreateSpec | MarvelLcgCreateSpec


@runtime_checkable
class GamePlatform(Protocol):
    """Transport contract for one playable game platform."""

    slug: PlatformSlug
    move_surface: MoveSurface
    uses_plugin: bool
    supports_room_close: bool
    state_reads_are_reader_sensitive: bool

    def new_session(self) -> "GamePlatform": ...

    async def authenticate(self) -> Any: ...

    async def create_table(self, identity: Any, spec: PlatformCreateSpec) -> Any: ...

    async def resolve_create_spec(
        self, spec: PlatformCreateSpec | None
    ) -> PlatformCreateSpec: ...

    async def setup_catalog(self) -> dict[str, Any]: ...

    async def attach_table(self, room_slug: str, identity: Any) -> Any: ...

    async def connect(self, room_slug: str, identity: Any) -> Any: ...

    def register_state_handlers(
        self,
        *,
        on_full_state: Callable[[Any], None],
        on_state_update: Callable[[Any], None],
        on_bad_game_state: Callable[[Any], None],
        on_state_unavailable: Callable[[Any], None],
        on_alert: Callable[[Any], None],
        on_gui_update: Callable[[Any], None],
        on_terminal: Callable[[Any], None],
    ) -> None: ...

    async def request_state(
        self, timeout: float, player_n: str | None = None
    ) -> Any: ...

    async def execute_move(self, move: Any, timeout: float) -> Any: ...

    async def wait_for_move(self, timeout: float) -> Any: ...

    async def list_options(self, player_n: str) -> Any: ...

    async def choose_option(
        self,
        player_n: str,
        *,
        option_id: int | str | None = None,
        targets: list[int | str] | None = None,
        resources: list[int | str] | None = None,
        decline: bool = False,
        prompt_id: str | None = None,
        prompt_version: int | None = None,
    ) -> Any: ...

    async def list_scenarios(self) -> list[str]: ...

    async def list_starter_deck(self) -> list[str]: ...

    async def set_seat(self, player_id: str, user_id: int) -> None: ...

    async def set_spectator(self, user_id: int, spectating: bool) -> None: ...

    async def push_event(
        self, event: str, payload: dict[str, Any], timeout: float
    ) -> Any: ...

    async def teardown(self, room_slug: str) -> None: ...

    def normalise_state(
        self,
        state: Any,
        *,
        plugin_name: str | None = None,
        player_n: str | None = None,
    ) -> Any: ...

    def configure_history(self, emitter: Any, session_id: str) -> None: ...

    def action_catalog(self) -> dict[str, Any]: ...

    def session_metadata(
        self,
        *,
        plugin_name: str,
        plugin_id: int | None,
        plugin_version: int | None,
    ) -> dict[str, Any]: ...

    def ensure_move_allowed(self) -> None: ...

    @staticmethod
    def build_set_game_payload(
        game: dict[str, Any], timestamp: int | None = None
    ) -> dict[str, Any]: ...

    @staticmethod
    def raise_for_bad_game_state(state: Any) -> None: ...


class DragnCardsPlatform:
    """DragnCards implementation of :class:`GamePlatform`.

    The object stored in the platform registry is a configuration/factory object.
    ``new_session`` returns a fresh driver so two sessions never share a Phoenix
    socket.  Existing DragnCards event names and payloads are kept here exactly
    as they were on the old ``PhoenixRoom`` path.
    """

    slug: PlatformSlug = DRAGNCARDS_PLATFORM
    move_surface: MoveSurface = "typed_actions"
    uses_plugin = True
    supports_room_close = True
    state_reads_are_reader_sensitive = False

    def __init__(
        self,
        http_url: str | None = None,
        ws_url: str | None = None,
        *,
        email: str | None = None,
        password: str | None = None,
        auth_cache: DragnCardsAuthCache | None = None,
        client: PhoenixClient | None = None,
        channel: Channel | None = None,
        create_room_fn: Callable[..., Any] = create_room,
        phoenix_client_cls: type[PhoenixClient] | None = None,
    ) -> None:
        self.http_url = http_url
        self.ws_url = ws_url
        self.email = email
        self.password = password
        self.auth_cache = auth_cache
        self._client = client
        self._channel = channel
        self._create_room = create_room_fn
        self._phoenix_client_cls = phoenix_client_cls or PhoenixClient

    def new_session(self) -> "DragnCardsPlatform":
        """Return an unconnected driver sharing only immutable configuration."""
        return DragnCardsPlatform(
            self.http_url,
            self.ws_url,
            email=self.email,
            password=self.password,
            auth_cache=self.auth_cache,
            create_room_fn=self._create_room,
            phoenix_client_cls=self._phoenix_client_cls,
        )

    @property
    def client(self) -> PhoenixClient | None:
        return self._client

    @property
    def channel(self) -> Channel | None:
        return self._channel

    async def authenticate(self) -> DragnCardsIdentity:
        if self.auth_cache is None:
            if self.http_url is None or self.email is None or self.password is None:
                raise ValueError("DragnCards credentials are not configured")
            self.auth_cache = DragnCardsAuthCache(
                self.http_url, self.email, self.password, ttl_seconds=0
            )
        return await self.auth_cache.resolve()

    async def create_table(
        self, identity: DragnCardsIdentity, spec: PlatformCreateSpec
    ) -> dict[str, Any]:
        if not isinstance(spec, DragnCardsCreateSpec):
            raise SessionError(
                "Platform 'dragncards' requires a DragnCards creation specification"
            )
        plugin_info = spec.plugin_info
        if self.http_url is None:
            raise ValueError("DragnCards HTTP URL is not configured")
        return await self._create_room(
            self.http_url,
            identity.token,
            user_id=identity.user_id,
            plugin_id=plugin_info["id"],
            plugin_version=plugin_info["version"],
            plugin_name=plugin_info["name"],
        )

    async def resolve_create_spec(
        self, spec: PlatformCreateSpec | None
    ) -> DragnCardsCreateSpec:
        if spec is None:
            raise SessionError("DragnCards creation requires a plugin selection")
        if not isinstance(spec, DragnCardsCreateSpec):
            raise SessionError(
                "Platform 'dragncards' cannot use a marvel-lcg creation specification"
            )
        return spec

    async def setup_catalog(self) -> dict[str, Any]:
        from game_service.catalog.service import supported_plugins

        return {
            "platform": self.slug,
            "move_surface": self.move_surface,
            "plugins": [
                {"id": plugin, "name": plugin, "display_name": plugin}
                for plugin in supported_plugins()
            ],
            "scenarios": [],
            "hero_decks": [],
        }

    async def attach_table(
        self, room_slug: str, identity: DragnCardsIdentity
    ) -> dict[str, Any]:
        del identity
        return {"slug": room_slug}

    async def connect(self, room_slug: str, identity: DragnCardsIdentity) -> Any:
        if self.ws_url is None:
            raise ValueError("DragnCards WebSocket URL is not configured")
        self._client = self._phoenix_client_cls(self.ws_url, auth_token=identity.token)
        try:
            await self._client.connect()
            self._channel = await self._client.join(f"room:{room_slug}")
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError from exc
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc
        if getattr(self._channel, "room_unavailable", False):
            await self._on_room_unavailable(identity)
            return None
        try:
            return await self._channel.wait_for_state_update(timeout=15.0)
        except asyncio.TimeoutError:
            return None
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc
        finally:
            if getattr(self._channel, "room_unavailable", False):
                await self._on_room_unavailable(identity)

    async def _on_room_unavailable(self, identity: DragnCardsIdentity) -> None:
        if identity.cached and self.auth_cache is not None:
            await self.auth_cache.invalidate()

    def register_state_handlers(
        self,
        *,
        on_full_state: Callable[[Any], None],
        on_state_update: Callable[[Any], None],
        on_bad_game_state: Callable[[Any], None],
        on_state_unavailable: Callable[[Any], None],
        on_alert: Callable[[Any], None],
        on_gui_update: Callable[[Any], None],
        on_terminal: Callable[[Any], None],
    ) -> None:
        del on_terminal
        if self._channel is None:
            raise RuntimeError("DragnCards driver is not connected")
        self._channel.on("current_state", on_full_state)
        self._channel.on("state_update", on_state_update)
        self._channel.on("bad_game_state", on_bad_game_state)
        for event_name in (
            "unable_to_get_state_on_join",
            "unable_to_get_state_on_request",
        ):
            self._channel.on(event_name, on_state_unavailable)
        self._channel.on("send_alert", on_alert)
        self._channel.on("gui_update", on_gui_update)

    async def request_state(self, timeout: float, player_n: str | None = None) -> Any:
        del player_n
        if self._channel is None:
            raise PhoenixChannelError("DragnCards room is not connected")
        try:
            await self._channel.push("request_state", {}, timeout=timeout)
            return await self._channel.wait_for_state_update(timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError from exc
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc

    # Legacy method names remain as thin aliases.  They are also useful to
    # callers that still hold a PhoenixRoom-shaped driver during rollout.
    async def execute_game_action(
        self, payload: dict[str, Any], timeout: float
    ) -> None:
        if self._channel is None:
            raise PhoenixChannelError("DragnCards room is not connected")
        try:
            await self._channel.push("game_action", payload, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError from exc
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc

    async def execute_move(self, move: Any, timeout: float) -> None:
        if isinstance(move, dict):
            payload = move
        else:
            # Keep typed-action translation at the platform boundary.  The
            # session owns game semantics, while only this driver knows that
            # DragnCards expects the Phoenix ``game_action`` payload.
            from game_service.logic.actions import translate_action

            payload = translate_action(move)
        await self.execute_game_action(payload, timeout=timeout)

    async def list_options(self, player_n: str) -> Any:
        del player_n
        raise EnumeratedOptionError(
            "Platform 'dragncards' offers typed actions, not enumerated options"
        )

    async def choose_option(self, player_n: str, **kwargs: Any) -> Any:
        del player_n, kwargs
        raise EnumeratedOptionError(
            "Platform 'dragncards' offers typed actions, not enumerated options"
        )

    async def list_scenarios(self) -> list[str]:
        raise SessionError("Platform 'dragncards' has no marvel-lcg scenario catalog")

    async def list_starter_deck(self) -> list[str]:
        raise SessionError("Platform 'dragncards' has no marvel-lcg deck catalog")

    async def wait_for_state_change(self, timeout: float) -> None:
        if self._channel is None:
            raise PhoenixChannelError("DragnCards room is not connected")
        try:
            await self._channel.wait_for_event(
                "state_update", "current_state", timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError from exc
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc

    async def wait_for_move(self, timeout: float) -> None:
        await self.wait_for_state_change(timeout=timeout)

    async def push_room_event(
        self, event: str, payload: dict[str, Any], timeout: float
    ) -> Any:
        if self._channel is None:
            raise PhoenixChannelError("DragnCards room is not connected")
        try:
            return await self._channel.push(event, payload, timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError from exc
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc

    async def push_event(
        self, event: str, payload: dict[str, Any], timeout: float
    ) -> Any:
        return await self.push_room_event(event, payload, timeout=timeout)

    async def send_room_event(self, event: str, payload: dict[str, Any]) -> None:
        if self._client is None or self._channel is None:
            raise PhoenixChannelError("DragnCards room is not connected")
        msg = PhxMessage(
            join_ref=self._channel.join_ref,
            ref=self._client._next_ref(),
            topic=self._channel.topic,
            event=event,
            payload=payload,
        )
        try:
            await self._client._send(msg)
        except PhoenixChannelError as exc:
            raise PlatformTransportError from exc

    async def send_event(self, event: str, payload: dict[str, Any]) -> None:
        await self.send_room_event(event, payload)

    async def set_seat(self, player_id: str, user_id: int) -> None:
        await self.send_room_event(
            "set_seat",
            {
                "player_i": player_id,
                "new_user_id": user_id,
                "timestamp": int(time.time() * 1000),
            },
        )

    async def set_spectator(self, user_id: int, spectating: bool) -> None:
        await self.send_room_event(
            "set_spectator", {"user_id": user_id, "value": spectating}
        )

    async def teardown(self, room_slug: str) -> None:
        if self._client is None:
            return
        await self._client.leave(f"room:{room_slug}")
        await self._client.disconnect()

    def normalise_state(
        self,
        state: Any,
        *,
        plugin_name: str | None = None,
        player_n: str | None = None,
    ) -> Any:
        from game_service.logic.normalisers import DragnCardsNormaliser

        return DragnCardsNormaliser().normalise(
            state,
            plugin_name=plugin_name,
            player_n=player_n,
        )

    def configure_history(self, emitter: Any, session_id: str) -> None:
        del emitter, session_id

    def action_catalog(self) -> dict[str, Any]:
        from game_service.api.routers.meta import build_generic_action_catalog

        actions, raw_ops = build_generic_action_catalog()
        return {
            "actions": actions,
            "raw_ops": raw_ops,
            "load_groups": [],
            "plugin_metadata": None,
        }

    def session_metadata(
        self,
        *,
        plugin_name: str,
        plugin_id: int | None,
        plugin_version: int | None,
    ) -> dict[str, Any]:
        return {
            "platform": self.slug,
            "move_surface": self.move_surface,
            "plugin_name": plugin_name,
            "plugin_id": plugin_id,
            "plugin_version": plugin_version,
        }

    def ensure_move_allowed(self) -> None:
        return None

    @staticmethod
    def build_set_game_payload(
        game: dict[str, Any], timestamp: int | None = None
    ) -> dict[str, Any]:
        """Build the legacy ``set_game`` payload without changing its shape."""
        return {
            "action": "set_game",
            "options": {"game": game, "description": "Load game state snapshot"},
            "timestamp": int(time.time() * 1000) if timestamp is None else timestamp,
        }

    @staticmethod
    def find_bad_game_state_message(state: Any) -> str | None:
        if not isinstance(state, dict):
            return None
        game = state.get("game")
        if not isinstance(game, dict) or not isinstance(game.get("messages"), list):
            return None
        for message in reversed(game["messages"]):
            if isinstance(message, str) and (
                "ABORT:" in message or "Error in Marvel Champions triggered" in message
            ):
                return message
        return None

    @classmethod
    def raise_for_bad_game_state(cls, state: Any) -> None:
        message = cls.find_bad_game_state_message(state)
        if message is not None:
            raise BadGameStateError(message)

    def check_bad_game_state(self, state: Any) -> None:
        self.raise_for_bad_game_state(state)


def create_legacy_dragncards_platform(client: Any, channel: Any) -> GamePlatform:
    """Create the deprecated test-only DragnCards handle adapter.

    Production session creation always supplies a driver from the registry. This
    narrow factory keeps older unit fixtures able to construct a session without
    making Phoenix transport types part of ``GameSession``'s public annotations.
    """
    return DragnCardsPlatform(client=client, channel=channel)
