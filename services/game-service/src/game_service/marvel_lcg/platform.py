"""Game-service driver for the vendored marvel-lcg engine."""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib.parse import urlsplit

from game_service.logic.exceptions import (
    BadGameStateError,
    EnumeratedOptionError,
    PlatformTimeoutError,
    PlatformTransportError,
    SessionError,
)
from game_service.logic.platform import (
    HeroDeckSelection,
    MARVEL_LCG_PLATFORM,
    MarvelLcgCreateSpec,
    MoveSurface,
    PlatformCreateSpec,
    PlatformSlug,
)
from game_service.logic.seats import normalise_seat_id, require_contiguous_seat_roster
from game_service.marvel_lcg.client import MarvelLcgHttpClient, NewGameDescriptor
from game_service.marvel_lcg.frames import (
    FrameDescriptor,
    MarvelLcgRenderSocket,
    PromptAttemptGuard,
    PromptSignature,
    StuckPromptError,
)
from game_service.marvel_lcg.normalizer import MarvelLcgNormaliser
from game_service.marvel_lcg.options import GameOptions, build_options, normalise_prompt
from game_service.telemetry import get_tracer

tracer = get_tracer(__name__)


@dataclass(frozen=True)
class MarvelLcgIdentity:
    session_token: str | None
    user_id: int | None = None


class MarvelLcgPlatform:
    """Adapter that hides HTTP, render frames, and zero-based seats."""

    slug: PlatformSlug = MARVEL_LCG_PLATFORM
    move_surface: MoveSurface = "enumerated_options"
    uses_plugin = False
    supports_room_close = False

    def __init__(
        self,
        http_url: str,
        password: str = "",
        *,
        ws_url: str | None = None,
        scenario_path: str | None = None,
        hero_paths: Iterable[str] = (),
        encounter_set_names: Iterable[str] = (),
        seats: Iterable[str] = ("player1",),
        max_submission_attempts: int = 3,
        ready_timeout: float = 30.0,
        move_timeout: float = 30.0,
        http_client: MarvelLcgHttpClient | None = None,
        http_client_factory: Callable[[], MarvelLcgHttpClient] | None = None,
        websocket_factory: Callable[..., Awaitable[Any]] | None = None,
    ) -> None:
        if not isinstance(password, str) or not password.strip():
            raise ValueError("MARVEL_LCG_PASSWORD must be non-empty")
        self.http_url = self._validate_http_url(http_url)
        configured_ws = ws_url or self.http_url.replace("http://", "ws://", 1).replace(
            "https://", "wss://", 1
        )
        websocket_url = (
            configured_ws
            if configured_ws.rstrip("/").endswith("/ws")
            else configured_ws.rstrip("/") + "/ws"
        )
        self.ws_url = self._validate_ws_url(websocket_url)
        self.password = password
        self.scenario_path = scenario_path
        self.hero_paths = tuple(hero_paths)
        self.encounter_set_names = tuple(encounter_set_names)
        self.held_seats = tuple(normalise_seat_id(seat) for seat in seats)
        if not self.held_seats:
            raise ValueError("marvel-lcg requires at least one held seat")
        self.max_submission_attempts = max_submission_attempts
        self.ready_timeout = ready_timeout
        self.move_timeout = move_timeout
        self._http_client = http_client or MarvelLcgHttpClient(http_url, password)
        self._http_client_factory = http_client_factory
        self._websocket_factory = websocket_factory
        self._socket: MarvelLcgRenderSocket | None = None
        self._sockets: dict[str, MarvelLcgRenderSocket] = {}
        self._room_slug = ""
        self._table_created = False
        self._latest_frame: FrameDescriptor | None = None
        self._latest_world: dict[str, Any] | None = None
        self._pending: dict[str, tuple[PromptSignature, GameOptions]] = {}
        self._attempt_guard = PromptAttemptGuard(max_submission_attempts)
        self._handlers: dict[str, Callable[[Any], Any]] = {}
        self._bad_state = False
        self._terminal = False
        self._terminal_recorded = False
        self._processed_frame_key: tuple[Any, ...] | None = None
        self._latest_frames: dict[int, FrameDescriptor] = {}
        self._acked_render_ids: dict[int, int] = {}
        self._degraded_seats: set[int] = set()
        self._prompt_events: set[PromptSignature] = set()
        self.normaliser = MarvelLcgNormaliser(
            self.held_seats, reading_seat=self.held_seats[0]
        )
        self.history_emitter: Any = None
        self.session_id: str | None = None
        self.selected_setup: MarvelLcgCreateSpec | None = None
        self._scenario_paths_by_id: dict[str, str] = {}
        self._hero_paths_by_id: dict[str, str] = {}
        self._last_resolved_spec: MarvelLcgCreateSpec | None = None
        self._lease_lost = False
        self._lease_validator: Callable[[], Awaitable[bool]] | None = None

    @staticmethod
    def _validate_http_url(value: str) -> str:
        parsed = urlsplit(value.strip() if isinstance(value, str) else "")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("marvel-lcg HTTP URL must be an absolute HTTP URL")
        if parsed.query or parsed.fragment:
            raise ValueError(
                "marvel-lcg HTTP URL must not contain query or fragment data"
            )
        return value.strip().rstrip("/")

    @staticmethod
    def _validate_ws_url(value: str) -> str:
        parsed = urlsplit(value.strip() if isinstance(value, str) else "")
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            raise ValueError("marvel-lcg WebSocket URL must be an absolute ws URL")
        if parsed.query or parsed.fragment:
            raise ValueError(
                "marvel-lcg WebSocket URL must not contain query or fragment data"
            )
        lowered = value.lower()
        if any(
            token in lowered
            for token in ("debug", "cheat", "show", "replay", "hot_seat")
        ):
            raise ValueError(
                "marvel-lcg debug and alternate-mode WebSocket URLs are forbidden"
            )
        return value.rstrip("/")

    def new_session(self) -> "MarvelLcgPlatform":
        client = self._http_client_factory() if self._http_client_factory else None
        return MarvelLcgPlatform(
            self.http_url,
            self.password,
            ws_url=self.ws_url,
            scenario_path=self.scenario_path,
            hero_paths=self.hero_paths,
            encounter_set_names=self.encounter_set_names,
            seats=self.held_seats,
            max_submission_attempts=self.max_submission_attempts,
            ready_timeout=self.ready_timeout,
            move_timeout=self.move_timeout,
            http_client=client,
            http_client_factory=self._http_client_factory,
            websocket_factory=self._websocket_factory,
        )

    async def authenticate(self) -> MarvelLcgIdentity:
        token = await self._http_client.authenticate()
        return MarvelLcgIdentity(session_token=token)

    async def list_scenarios(self) -> list[str]:
        return await self._http_client.list_scenarios()

    async def list_starter_deck(self) -> list[str]:
        return await self._http_client.list_starter_deck()

    @staticmethod
    def _catalog_id(kind: str, source_path: str) -> str:
        digest = hashlib.sha256(f"{kind}:{source_path}".encode("utf-8")).hexdigest()
        return f"{kind}:{digest[:24]}"

    @staticmethod
    def _display_name(source_path: str) -> str:
        name = os.path.basename(source_path).rsplit(".", 1)[0]
        return name.replace("_", " ").replace("-", " ").strip() or source_path

    async def setup_catalog(self) -> dict[str, Any]:
        scenarios = await self._http_client.list_scenarios()
        hero_decks = await self._http_client.list_starter_deck()
        return {
            "platform": self.slug,
            "move_surface": self.move_surface,
            "scenarios": [
                {
                    "id": self._catalog_id("scenario", path),
                    "name": self._display_name(path),
                    "display_name": self._display_name(path),
                }
                for path in scenarios
            ],
            "hero_decks": [
                {
                    "id": self._catalog_id("hero-deck", path),
                    "name": self._display_name(path),
                    "display_name": self._display_name(path),
                }
                for path in hero_decks
            ],
        }

    async def resolve_create_spec(
        self, spec: PlatformCreateSpec | None
    ) -> MarvelLcgCreateSpec:
        scenarios = await self._http_client.list_scenarios()
        decks = await self._http_client.list_starter_deck()
        scenario_by_id = {
            self._catalog_id("scenario", path): path for path in scenarios
        }
        hero_by_id = {self._catalog_id("hero-deck", path): path for path in decks}
        self._scenario_paths_by_id = scenario_by_id
        self._hero_paths_by_id = hero_by_id

        if spec is None:
            configured_scenario = self.scenario_path
            configured_heroes = self.hero_paths
            if configured_scenario is None or not configured_heroes:
                raise SessionError(
                    "marvel-lcg setup is not configured; call list_game_setup_catalog "
                    "and provide scenario_id plus ordered hero_decks"
                )
            scenario_id = (
                configured_scenario
                if configured_scenario in scenario_by_id
                else self._catalog_id("scenario", configured_scenario)
            )
            if scenario_id not in scenario_by_id:
                raise SessionError(
                    "Configured MARVEL_LCG_SCENARIO_PATH is absent from the live "
                    "setup catalog; call list_game_setup_catalog for valid scenario_id"
                )
            hero_decks = tuple(
                HeroDeckSelection(
                    seat=f"player{index}",
                    hero_deck_id=(
                        path
                        if path in hero_by_id
                        else self._catalog_id("hero-deck", path)
                    ),
                )
                for index, path in enumerate(configured_heroes, start=1)
            )
            spec = MarvelLcgCreateSpec(
                platform=MARVEL_LCG_PLATFORM,
                scenario_id=scenario_id,
                hero_decks=hero_decks,
            )

        if not isinstance(spec, MarvelLcgCreateSpec):
            raise SessionError(
                "Platform 'marvel-lcg' cannot use a DragnCards creation specification"
            )
        if spec.scenario_id not in scenario_by_id:
            raise SessionError(
                f"Unknown marvel-lcg scenario_id {spec.scenario_id!r}; "
                "call list_game_setup_catalog first"
            )
        if not spec.hero_decks:
            raise SessionError(
                "marvel-lcg setup requires at least one ordered hero_decks entry"
            )

        seats: list[str] = []
        for selection in spec.hero_decks:
            try:
                seat = normalise_seat_id(selection.seat)
            except (TypeError, ValueError) as exc:
                raise SessionError(
                    f"Invalid marvel-lcg seat {selection.seat!r}; expected player1..player4"
                ) from exc
            if seat in seats:
                raise SessionError(f"Duplicate marvel-lcg seat {seat!r}")
            seats.append(seat)
            if selection.hero_deck_id not in hero_by_id:
                raise SessionError(
                    f"Unknown marvel-lcg hero_deck_id {selection.hero_deck_id!r}; "
                    "call list_game_setup_catalog first"
                )

        try:
            require_contiguous_seat_roster(seats)
        except ValueError as exc:
            raise SessionError(str(exc)) from exc

        resolved = MarvelLcgCreateSpec(
            platform=MARVEL_LCG_PLATFORM,
            scenario_id=spec.scenario_id,
            hero_decks=tuple(
                HeroDeckSelection(
                    seat=normalise_seat_id(selection.seat),
                    hero_deck_id=selection.hero_deck_id,
                )
                for selection in spec.hero_decks
            ),
        )
        self._last_resolved_spec = resolved
        return resolved

    async def create_table(
        self, identity: MarvelLcgIdentity, spec: PlatformCreateSpec
    ) -> dict[str, Any]:
        del identity
        resolved = (
            self._last_resolved_spec
            if self._last_resolved_spec is not None and self._last_resolved_spec == spec
            else await self.resolve_create_spec(spec)
        )
        scenario = self._scenario_paths_by_id[resolved.scenario_id]
        selections = tuple(resolved.hero_decks)
        heroes = tuple(self._hero_paths_by_id[item.hero_deck_id] for item in selections)
        self.held_seats = tuple(item.seat for item in selections)
        self.normaliser = MarvelLcgNormaliser(
            self.held_seats, reading_seat=self.held_seats[0]
        )
        self.selected_setup = resolved
        campaign_json = await self._http_client.get_scenario_json(scenario)
        hero_json = [await self._http_client.get_hero_json(path) for path in heroes]
        descriptor = NewGameDescriptor(
            campaign_json=campaign_json,
            encounter_set_names=list(self.encounter_set_names),
            hero_json=hero_json,
            seed=0,
            timeout=0,
            challenges=[],
            rules=["v18_all"],
            campaign_log={},
        )
        with tracer.start_as_current_span(
            "marvel_lcg.create_game",
            attributes={
                "game.platform": "marvel-lcg",
                "game.hero.count": len(hero_json),
                "game.encounter_set.count": len(descriptor.encounter_set_names),
            },
        ) as span:
            result = await self._http_client.new_game(descriptor)
            if result.get("result") != "New game created":
                span.set_attribute("game.outcome", "rejected")
                raise SessionError("marvel-lcg could not create a table")
            span.set_attribute("game.outcome", "created")
        # The fork has one active game and does not return a room id. The slug is
        # local coordination metadata, never sent to the engine.
        self._room_slug = f"marvel-lcg-{uuid.uuid4()}"
        self._table_created = True
        return {"slug": self._room_slug, **result}

    async def attach_table(
        self, room_slug: str, identity: MarvelLcgIdentity
    ) -> dict[str, Any]:
        del identity
        self._room_slug = room_slug
        self._table_created = True
        return {"slug": room_slug}

    def _seat_number(self, player_n: str) -> int:
        player_n = normalise_seat_id(player_n)
        return int(player_n[6:]) - 1

    async def connect(
        self, room_slug: str, identity: MarvelLcgIdentity
    ) -> dict[str, Any]:
        del identity
        self._room_slug = room_slug
        if not self._table_created:
            raise SessionError(
                "marvel-lcg session must create or attach a table before connecting"
            )
        for socket in self._sockets.values():
            await socket.close()
        self._sockets.clear()
        for player_n in self.held_seats:
            socket = MarvelLcgRenderSocket(
                self.ws_url,
                seat=self._seat_number(player_n),
                cookie_header=self._http_client.cookie_header(),
                handshake_url=self.http_url + "/",
                websocket_factory=self._websocket_factory,
                on_frame=self._on_background_frame,
            )
            self._sockets[player_n] = socket
        self._socket = self._sockets[self.held_seats[0]]
        with tracer.start_as_current_span(
            "marvel_lcg.socket.connect",
            attributes={
                "game.platform": "marvel-lcg",
                "game.seat.count": len(self.held_seats),
            },
        ) as span:
            try:
                await asyncio.gather(
                    *(socket.open() for socket in self._sockets.values())
                )
                span.set_attribute("game.outcome", "connected")
            except asyncio.TimeoutError as exc:
                span.set_attribute("game.outcome", "timeout")
                raise PlatformTimeoutError from exc
            except OSError as exc:
                span.set_attribute("game.outcome", "transport_error")
                raise PlatformTransportError from exc
        frame = await self._wait_for_frame(
            lambda item: self._seat_number(self.held_seats[0]) in item.ask_players,
            self.ready_timeout,
        )
        await self._process_frame(frame)
        state = await self.request_state(timeout=self.ready_timeout)
        return state

    def register_state_handlers(self, **handlers: Callable[..., Any]) -> None:
        self._handlers = dict(handlers)

    async def _on_background_frame(self, frame: FrameDescriptor) -> None:
        await self._process_frame(frame)
        if frame.transport_degraded:
            return
        if self._acked_render_ids.get(frame.player_id) == frame.render_id:
            return
        self._acked_render_ids[frame.player_id] = frame.render_id
        try:
            await self._http_client.client_updated(
                f"player{frame.player_id + 1}", frame.render_id, frame.game_id
            )
        except Exception:
            # Frame acknowledgement is advisory; the next frame remains the
            # authoritative source of state.
            return

    async def _wait_for_frame(
        self, predicate: Callable[[FrameDescriptor], bool], timeout: float
    ) -> FrameDescriptor:
        if self._socket is None:
            raise SessionError("marvel-lcg render socket is not connected")
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise PlatformTimeoutError
            try:
                frame = await self._socket.wait_for_frame(remaining)
            except asyncio.TimeoutError as exc:
                raise PlatformTimeoutError from exc
            if frame.transport_degraded:
                raise PlatformTransportError("marvel-lcg render transport is degraded")
            self._latest_frame = frame
            if frame.game_over:
                await self._process_frame(frame)
                return frame
            if predicate(frame):
                return frame

    def _raw_state(self) -> dict[str, Any]:
        if self._latest_world is None:
            raise SessionError("marvel-lcg has not returned a world yet")
        state = dict(self._latest_world)
        if self._latest_frame is not None:
            state["_frame"] = self._latest_frame.__dict__
            state["_ask_players"] = list(self._latest_frame.ask_players)
        return state

    async def _process_frame(self, frame: FrameDescriptor) -> None:
        self._latest_frame = frame
        self._latest_frames[frame.player_id] = frame
        if frame.transport_degraded:
            if frame.player_id not in self._degraded_seats:
                self._degraded_seats.add(frame.player_id)
                callback = self._handlers.get("on_state_unavailable")
                if callback is not None:
                    callback(
                        {
                            "seat": frame.player_id,
                            "reason": "marvel-lcg render transport degraded",
                        }
                    )
            return
        frame_key = (
            frame.render_id,
            frame.game_id,
            frame.ask_players,
            frame.current_step_id,
            frame.debug_message,
        )
        if self._processed_frame_key == frame_key:
            return
        self._processed_frame_key = frame_key
        if frame.game_over:
            if self._terminal_recorded:
                return
            self._terminal_recorded = True
            self._terminal = True
            await self._emit_platform_event("terminal", {})
            callback = self._handlers.get("on_terminal")
            if callback is not None:
                callback({"render_id": frame.render_id})
            return
        callback = self._handlers.get("on_state_update")
        if callback is not None:
            callback(
                self._raw_state() if self._latest_world is not None else frame.__dict__
            )

    async def request_state(
        self, timeout: float, player_n: str | None = None
    ) -> dict[str, Any]:
        del timeout
        if player_n is not None:
            self._require_held_seat(player_n)
        self._check_bad_state()
        self._check_transport()
        if self._socket is None:
            raise SessionError("marvel-lcg render socket is not connected")
        seat = normalise_seat_id(player_n or self.held_seats[0])
        with tracer.start_as_current_span(
            "marvel_lcg.world",
            attributes={"game.platform": "marvel-lcg", "game.seat": seat},
        ):
            world = await self._http_client.get_world(seat)
        self.raise_for_bad_game_state(world)
        self._latest_world = world
        frame = self._latest_frames.get(self._seat_number(seat))
        if frame is not None:
            self._acked_render_ids[self._seat_number(seat)] = frame.render_id
            try:
                await self._http_client.client_updated(
                    seat, frame.render_id, frame.game_id
                )
            except Exception:
                # Acknowledgement is best-effort; the next frame still gives us
                # an authoritative render id.
                pass
        callback = self._handlers.get("on_full_state")
        if callback is not None:
            callback(self._raw_state())
        return self._raw_state()

    async def execute_move(self, move: Any, timeout: float) -> Any:
        del move, timeout
        raise EnumeratedOptionError(
            "Platform 'marvel-lcg' offers enumerated options; use list_game_options "
            "and choose_game_option instead of typed actions"
        )

    async def wait_for_move(self, timeout: float) -> Any:
        if self._socket is None:
            raise SessionError("marvel-lcg render socket is not connected")
        try:
            frame = await self._socket.wait_for_frame(timeout)
        except asyncio.TimeoutError as exc:
            raise PlatformTimeoutError from exc
        if frame.transport_degraded:
            raise PlatformTransportError("marvel-lcg render transport is degraded")
        await self._process_frame(frame)
        if frame.game_over:
            return await self.request_state(timeout)
        return await self.request_state(timeout)

    def _signature(self, player_n: str, options: GameOptions) -> PromptSignature:
        frame = (
            self._latest_frames.get(self._seat_number(player_n)) or self._latest_frame
        )
        return PromptSignature(
            render_id=frame.render_id if frame is not None else 0,
            ask_players=tuple(
                sorted(
                    frame.ask_players
                    if frame is not None
                    else (self._seat_number(player_n),)
                )
            ),
            prompt_text=normalise_prompt(options.prompt),
            option_ids=tuple(sorted({str(option.id) for option in options.options})),
        )

    @staticmethod
    def _prompt_identity(signature: PromptSignature, player_n: str) -> tuple[str, int]:
        material = "|".join(
            [
                str(signature.render_id),
                ",".join(str(item) for item in signature.ask_players),
                signature.prompt_text,
                ",".join(signature.option_ids),
            ]
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"{player_n}:{signature.render_id}", int(digest[:8], 16)

    async def list_options(self, player_n: str) -> GameOptions:
        player_n = normalise_seat_id(player_n)
        self._require_held_seat(player_n)
        self._check_bad_state()
        seat = self._seat_number(player_n)
        self._pending.pop(player_n, None)
        with tracer.start_as_current_span(
            "marvel_lcg.read_options",
            attributes={"game.platform": "marvel-lcg", "game.seat": player_n},
        ) as span:
            await self.request_state(timeout=self.move_timeout, player_n=player_n)
            ask = await self._http_client.get_ask(player_n)
            if ask is None:
                span.set_attribute("game.option.count", 0)
                span.set_attribute("game.prompt.present", False)
                return GameOptions(player_n=player_n, asked_seats=[], options=[])
            assert self._latest_world is not None
            frame = self._latest_frames.get(seat) or self._latest_frame
            ask["ask_players"] = list(frame.ask_players) if frame else [seat]
            options = build_options(
                ask,
                self._latest_world,
                player_n=player_n,
                visible_seats=(seat,),
            )
            span.set_attribute("game.option.count", len(options.options))
            span.set_attribute("game.prompt.present", bool(options.prompt))
            options.session_id = self.session_id
            signature = self._signature(player_n, options)
            options.prompt_id, options.prompt_version = self._prompt_identity(
                signature, player_n
            )
            self._pending[player_n] = (signature, options)
            self._attempt_guard.clear_except(signature)
            if signature not in self._prompt_events:
                self._prompt_events.add(signature)
                await self._emit_platform_event(
                    "prompt",
                    {"player_n": player_n, "option_count": len(options.options)},
                )
            return options

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
    ) -> dict[str, Any]:
        player_n = normalise_seat_id(player_n)
        self._require_held_seat(player_n)
        self.ensure_move_allowed()
        if prompt_id is None or prompt_version is None:
            raise EnumeratedOptionError(
                "prompt_id and prompt_version are required for a choice"
            )
        options = await self.list_options(player_n)
        pending = self._pending.get(player_n)
        if pending is None:
            raise EnumeratedOptionError(f"Seat {player_n} has no pending decision")
        signature, pending_options = pending
        expected_id, expected_version = self._prompt_identity(signature, player_n)
        if prompt_id != expected_id or prompt_version != expected_version:
            raise EnumeratedOptionError("The requested prompt is stale")
        options = pending_options
        if not options.options:
            if not options.can_decline:
                raise EnumeratedOptionError(f"Seat {player_n} has no pending decision")
            if not decline:
                raise EnumeratedOptionError(
                    f"Prompt for {player_n} only supports declining"
                )
            chosen_id: int | str = 0
            chosen = None
        elif decline:
            if not options.can_decline:
                raise EnumeratedOptionError(f"Prompt for {player_n} cannot be declined")
            chosen_id: int | str = 0
            chosen = None
        else:
            if option_id is None:
                raise EnumeratedOptionError(
                    "An option id is required; option names are not accepted"
                )
            chosen = next(
                (item for item in options.options if str(item.id) == str(option_id)),
                None,
            )
            if chosen is None:
                pending = [str(item.id) for item in options.options]
                raise EnumeratedOptionError(
                    f"Option id {option_id!r} is not pending; pending ids={pending}"
                )
            chosen_id = chosen.id
        selected_targets = list(targets or [])
        selected_resources = list(resources or [])
        if chosen is not None:
            target_range = chosen.target_num_range
            if not target_range.valid_count(len(selected_targets)):
                raise EnumeratedOptionError(
                    f"Option {chosen.id!r} accepts {target_range.min}..{target_range.max} targets; got {selected_targets}"
                )
            if target_range.max == 0:
                selected_targets = []
            else:
                legal = {str(target.id) for target in chosen.targets}
                invalid = [
                    target for target in selected_targets if str(target) not in legal
                ]
                if invalid:
                    raise EnumeratedOptionError(
                        f"Option {chosen.id!r} does not permit targets {invalid}; legal targets={sorted(legal)}"
                    )
        with tracer.start_as_current_span(
            "marvel_lcg.submit_option",
            attributes={
                "game.platform": "marvel-lcg",
                "game.seat": player_n,
                "game.option.id": str(chosen_id),
                "game.target.count": len(selected_targets),
                "game.resource.count": len(selected_resources),
            },
        ) as span:
            try:
                await self.ensure_lease_owned()
                self._attempt_guard.raise_if_exhausted(signature)
                self._attempt_guard.record(signature, chosen_id)
                await self._http_client.post(
                    player_n, chosen_id, selected_targets, selected_resources
                )
                resolved = await self._wait_for_resolution(
                    player_n, signature, option_id=chosen_id
                )
            except Exception as exc:
                span.set_attribute("game.outcome", "failed")
                span.set_attribute("error.type", type(exc).__name__)
                raise
            span.set_attribute("game.outcome", "resolved" if resolved else "pending")
        return {"player_n": player_n, "option_id": chosen_id, "resolved": resolved}

    async def _wait_for_resolution(
        self, player_n: str, previous: PromptSignature, *, option_id: int | str
    ) -> bool:
        socket = self._sockets.get(player_n) or self._socket
        if socket is None:
            raise SessionError("marvel-lcg render socket is not connected")
        deadline = time.monotonic() + self.move_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StuckPromptError(
                    "marvel-lcg prompt did not resolve after "
                    f"{self._attempt_guard.attempts(previous)} attempts"
                )
            try:
                frame = await socket.wait_for_frame(remaining)
            except asyncio.TimeoutError as exc:
                raise PlatformTimeoutError from exc
            if frame.transport_degraded:
                raise PlatformTransportError("marvel-lcg render transport is degraded")
            if frame.game_over:
                await self._emit_platform_event(
                    "move",
                    {
                        "player_n": player_n,
                        "option_id": option_id,
                        "resolved": True,
                    },
                )
                await self._process_frame(frame)
                return True
            await self._process_frame(frame)
            if self._seat_number(player_n) not in frame.ask_players:
                self._pending.pop(player_n, None)
                self._attempt_guard.clear(previous)
                await self.request_state(remaining, player_n=player_n)
                await self._emit_platform_event(
                    "move",
                    {
                        "player_n": player_n,
                        "option_id": option_id,
                        "resolved": True,
                    },
                )
                return True
            ask = await self._http_client.get_ask(player_n)
            if ask is None:
                self._pending.pop(player_n, None)
                self._attempt_guard.clear(previous)
                await self.request_state(remaining, player_n=player_n)
                await self._emit_platform_event(
                    "move",
                    {
                        "player_n": player_n,
                        "option_id": option_id,
                        "resolved": True,
                    },
                )
                return True
            ask["ask_players"] = list(frame.ask_players)
            await self.request_state(remaining, player_n=player_n)
            assert self._latest_world is not None
            current = build_options(
                ask,
                self._latest_world,
                player_n=player_n,
                visible_seats=(self._seat_number(player_n),),
            )
            current_signature = self._signature(player_n, current)
            if current_signature != previous:
                self._pending[player_n] = (current_signature, current)
                await self.request_state(remaining, player_n=player_n)
                await self._emit_platform_event(
                    "move",
                    {
                        "player_n": player_n,
                        "option_id": option_id,
                        "resolved": True,
                    },
                )
                return True
            # The complete prompt identity repeated unchanged. This includes
            # render_id: a later render with the same visible prompt is a new
            # prompt, while an unchanged post-submission frame must consume the
            # configured retry budget rather than timing out.
            self._attempt_guard.raise_if_exhausted(previous)
            return False

    async def set_seat(self, player_id: str, user_id: int) -> None:
        del player_id, user_id
        raise SessionError("marvel-lcg seats are selected at the render-socket edge")

    async def set_spectator(self, user_id: int, spectating: bool) -> None:
        del user_id, spectating
        raise SessionError("marvel-lcg does not expose spectator controls")

    async def push_event(
        self, event: str, payload: dict[str, Any], timeout: float
    ) -> Any:
        del event, payload, timeout
        raise SessionError("marvel-lcg does not expose DragnCards room events")

    async def teardown(self, room_slug: str) -> None:
        del room_slug
        for socket in self._sockets.values():
            await socket.close()
        self._socket = None
        self._sockets.clear()
        await self._http_client.aclose()

    def normalise_state(
        self, state: Any, *, plugin_name: str | None = None
    ) -> dict[str, Any]:
        self._check_bad_state()
        try:
            return self.normaliser.normalise(state, plugin_name=plugin_name)
        except (TypeError, ValueError, KeyError) as exc:
            self._mark_bad_state(exc)
            raise BadGameStateError(
                "marvel-lcg returned an unnormalisable world"
            ) from exc

    def configure_history(self, emitter: Any, session_id: str) -> None:
        self.history_emitter = emitter
        self.session_id = session_id

    def action_catalog(self) -> dict[str, Any]:
        return {
            "actions": [],
            "raw_ops": [],
            "load_groups": [],
            "plugin_metadata": {
                "platform": MARVEL_LCG_PLATFORM,
                "move_surface": self.move_surface,
            },
        }

    def session_metadata(
        self,
        *,
        plugin_name: str,
        plugin_id: int | None,
        plugin_version: int | None,
    ) -> dict[str, Any]:
        del plugin_name, plugin_id, plugin_version
        setup = None
        if self.selected_setup is not None:
            setup = {
                "platform": self.selected_setup.platform,
                "scenario_id": self.selected_setup.scenario_id,
                "hero_decks": [
                    {
                        "seat": item.seat,
                        "hero_deck_id": item.hero_deck_id,
                    }
                    for item in self.selected_setup.hero_decks
                ],
            }
        return {
            "platform": self.slug,
            "move_surface": self.move_surface,
            "setup": setup,
        }

    def ensure_move_allowed(self) -> None:
        self._check_bad_state()
        if self._lease_lost:
            raise SessionError(
                "marvel-lcg singleton lease is lost; no further moves are allowed"
            )
        if self._terminal:
            raise SessionError("marvel-lcg game is terminal")

    def set_lease_validator(self, validator: Callable[[], Awaitable[bool]]) -> None:
        self._lease_validator = validator
        self._lease_lost = False

    def mark_lease_lost(self, reason: str = "marvel-lcg singleton lease lost") -> None:
        del reason
        self._lease_lost = True

    async def ensure_lease_owned(self) -> None:
        self.ensure_move_allowed()
        if self._lease_validator is None:
            return
        try:
            owned = await self._lease_validator()
        except Exception as exc:
            self.mark_lease_lost()
            raise SessionError(
                "marvel-lcg singleton lease could not be verified; no move was sent"
            ) from exc
        if not owned:
            self.mark_lease_lost()
            raise SessionError("marvel-lcg singleton lease is lost; no move was sent")

    def _require_held_seat(self, player_n: str) -> None:
        if normalise_seat_id(player_n) not in self.held_seats:
            raise SessionError(f"Seat {player_n} is not held by this session")

    @staticmethod
    def build_set_game_payload(
        game: dict[str, Any], timestamp: int | None = None
    ) -> dict[str, Any]:
        del game, timestamp
        raise SessionError(
            "marvel-lcg state snapshots cannot be loaded through DragnLang"
        )

    def raise_for_bad_game_state(self, state: Any) -> None:
        self._check_bad_state()
        if not isinstance(state, dict):
            error = BadGameStateError("marvel-lcg returned an unnormalisable world")
            self._mark_bad_state(error)
            raise error
        try:
            self.normaliser.normalise(state)
        except (TypeError, ValueError, KeyError) as exc:
            self._mark_bad_state(exc)
            raise BadGameStateError(
                "marvel-lcg returned an unnormalisable world"
            ) from exc

    def _mark_bad_state(self, cause: BaseException) -> None:
        del cause
        if self._bad_state:
            return
        self._bad_state = True
        callback = self._handlers.get("on_bad_game_state")
        if callback is not None:
            callback({"reason": "marvel-lcg returned an unnormalisable world"})

    def _check_bad_state(self) -> None:
        if self._bad_state:
            raise BadGameStateError("marvel-lcg game state is corrupted or unavailable")

    def _check_transport(self) -> None:
        if self._degraded_seats:
            seats = ", ".join(
                f"player{seat + 1}" for seat in sorted(self._degraded_seats)
            )
            raise PlatformTransportError(
                f"marvel-lcg render transport is degraded for {seats}"
            )

    async def _emit_platform_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> None:
        emitter = self.history_emitter
        method = getattr(emitter, "emit_platform_event", None)
        if method is None or self.session_id is None:
            return
        try:
            history_state = self._history_state()
            status = history_state.get("mode", "unknown")
            if event_type == "terminal":
                # A render_id of -1 is the transport's terminal marker, not a
                # history outcome. Preserve an explicit engine outcome and
                # normalize every other terminal observation to loss.
                status = status if status in {"win", "loss"} else "loss"
                history_state["mode"] = status
            event_payload = dict(payload)
            event_payload["state"] = history_state
            event_payload["status"] = status
            await method(
                game_id=self.session_id,
                platform=MARVEL_LCG_PLATFORM,
                event_type=event_type,
                payload=event_payload,
            )
        except Exception:
            # History is intentionally best effort and must not affect play.
            return

    def _history_state(self) -> dict[str, Any]:
        """Return the current Marvel state in the neutral history shape."""
        if self._latest_world is not None:
            source = self._raw_state()
        elif self._latest_frame is not None:
            source = {"_frame": self._latest_frame.__dict__}
        else:
            source = {}
        return self.normaliser.normalise(source)
