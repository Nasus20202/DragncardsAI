"""
Session pool manager.

SessionManager maintains a pool of active GameSession objects and is shared
by both the HTTP API and the MCP server. All public methods are async and safe
to call from concurrent request handlers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from game_service.dragncards.auth_cache import (
    DragnCardsAuthCache,
)
from game_service.dragncards.http_client import create_room
from game_service.catalog.service import get_plugin_action_catalog, load_prebuilt_deck
from game_service.coordination.history_emitter import (
    HistoryEmitter,
    NullHistoryEmitter,
)
from game_service.logic.exceptions import (
    AmbiguousSessionIdentifierError,
    BadGameStateError,
    SessionError,
    SessionLockedError,
    SessionNotFoundError,
    SingletonLeaseConflictError,
    SnapshotValidationError,
    StateUnavailableError,
)
from game_service.logic.seats import (
    normalise_seat_id,
    seat_occupants,
    seats_to_claim,
)
from game_service.logic.platform import (
    DRAGNCARDS_PLATFORM,
    DragnCardsCreateSpec,
    GamePlatform,
    HeroDeckSelection,
    MarvelLcgCreateSpec,
    PlatformSlug,
    DragnCardsPlatform,
)
from game_service.logic.session import GameSession
from game_service.coordination.session_store import InMemorySessionStore, SessionStore
from game_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


def _seat_number(player_n: str) -> int | None:
    """The 1-based seat number of a seat id like ``player3`` (-> 3)."""
    if not player_n.startswith("player"):
        return None
    try:
        return int(player_n[len("player") :])
    except ValueError:
        return None


def _layout_id_for_player_count(plugin_name: str, num_players: int) -> str | None:
    """The plugin layout for a player count, or None if the plugin has none.

    Derived from the plugin's player-count menu (e.g. Marvel Champions maps
    ``2`` to ``standard2Player``) so the count bump also switches the table
    layout to one that has regions for the new seat's groups.
    """
    catalog = get_plugin_action_catalog(plugin_name)
    for entry in catalog.player_count_layouts:
        if entry.num_players == num_players:
            return entry.layout_id
    return None


class SessionManager:
    """Maintains a pool of active GameSession objects."""

    def __init__(
        self,
        platform_registry: dict[str, GamePlatform] | None = None,
        plugin_registry: dict[str, dict] | None = None,
        session_store: SessionStore | None = None,
        history_emitter: HistoryEmitter | None = None,
        ephemeral_session_ttl_seconds: float = 1800.0,
        ephemeral_reaper_interval_seconds: float = 60.0,
        auth_cache: DragnCardsAuthCache | None = None,
        platform: GamePlatform | None = None,
        platforms: dict[str, GamePlatform] | None = None,
        # Deprecated compatibility arguments. They are used to construct the
        # DragnCards registry entry when callers have not moved to the seam yet.
        dragncards_http_url: str | None = None,
        dragncards_ws_url: str | None = None,
        email: str | None = None,
        password: str | None = None,
        marvel_lease_ttl_seconds: float = 30.0,
    ):
        self._plugin_registry = plugin_registry or {}
        if platform_registry is None and platforms is not None:
            platform_registry = platforms
        if platform_registry is None and platform is not None:
            platform_registry = {platform.slug: platform}
        if platform_registry is None:
            if dragncards_http_url is None:
                dragncards_http_url = "http://localhost:4000"
            if dragncards_ws_url is None:
                dragncards_ws_url = "ws://localhost:4000/socket"
            if email is None:
                email = "dev@example.com"
            if password is None:
                password = "dev_password"
            # An inert cache (no Valkey, or TTL 0) authenticates live on every
            # call, matching the manager's pre-platform behaviour.
            auth_cache = auth_cache or DragnCardsAuthCache(
                dragncards_http_url, email, password, ttl_seconds=0
            )
            platform_registry = {
                DRAGNCARDS_PLATFORM: DragnCardsPlatform(
                    dragncards_http_url,
                    dragncards_ws_url,
                    email=email,
                    password=password,
                    auth_cache=auth_cache,
                    create_room_fn=create_room,
                )
            }
        self._platform_registry = platform_registry
        dragncards = self._platform_registry.get(DRAGNCARDS_PLATFORM)
        self._auth_cache = auth_cache or getattr(dragncards, "auth_cache", None)
        # Read-only compatibility attributes for older diagnostic callers.
        self._http_url = getattr(dragncards, "http_url", dragncards_http_url)
        self._ws_url = getattr(dragncards, "ws_url", dragncards_ws_url)
        self._email = getattr(dragncards, "email", email)
        self._password = getattr(dragncards, "password", password)
        self._session_store = session_store or InMemorySessionStore()
        self._history_emitter = history_emitter or NullHistoryEmitter()
        self._sessions: dict[str, GameSession] = {}
        self._lock = asyncio.Lock()
        self._ephemeral_session_ttl_seconds = ephemeral_session_ttl_seconds
        self._ephemeral_reaper_interval_seconds = ephemeral_reaper_interval_seconds
        self._reaper_task: asyncio.Task[None] | None = None
        self._marvel_lease_ttl_seconds = marvel_lease_ttl_seconds
        self._marvel_lease_tasks: dict[str, asyncio.Task[None]] = {}
        self._marvel_leases: dict[str, tuple[str, str]] = {}
        self._marvel_lease_sessions: dict[str, GameSession] = {}
        self._marvel_lease_validators: dict[str, Any] = {}
        self._marvel_lease_lost: set[str] = set()

    async def restore_sessions(self) -> None:
        with tracer.start_as_current_span("game_service.restore_sessions"):
            records = await self._session_store.list_sessions()
            for record in records:
                session_id = record["session_id"]
                if session_id in self._sessions:
                    continue
                if record.get("platform", DRAGNCARDS_PLATFORM) == "marvel-lcg":
                    logger.warning(
                        "Skipping persisted marvel-lcg session %s: attachment is unsupported",
                        session_id,
                    )
                    await self._session_store.delete_session(session_id)
                    continue
                await self._restore_session(record)

    def _get_plugin_info(self, plugin_name: str) -> dict[str, Any]:
        plugin_info = self._plugin_registry.get(plugin_name)
        if plugin_info is None:
            available = list(self._plugin_registry.keys())
            raise SessionError(
                f"Plugin {plugin_name!r} not found. Available: {available}"
            )
        return plugin_info

    def _get_platform(self, platform: str) -> GamePlatform:
        driver = self._platform_registry.get(platform)
        if driver is None:
            available = list(self._platform_registry.keys())
            raise SessionError(
                f"Platform {platform!r} is not configured. Available: {available}"
            )
        return driver

    def _new_platform(self, platform: str) -> GamePlatform:
        driver = self._get_platform(platform)
        factory = getattr(driver, "new_session", None)
        session_driver = factory() if factory is not None else driver
        # The manager owns the cache lifecycle. The integration/bootstrap path
        # may install the Valkey-backed cache after the platform registry has
        # been constructed, so make each fresh DragnCards driver use the current
        # manager cache without sharing its transport or mutating the registry
        # driver. Other platforms must never receive DragnCards credentials.
        if (
            platform == DRAGNCARDS_PLATFORM
            and self._auth_cache is not None
            and isinstance(session_driver, DragnCardsPlatform)
        ):
            session_driver.auth_cache = self._auth_cache
        return session_driver

    async def _credentials(self, platform: str = DRAGNCARDS_PLATFORM) -> Any:
        """Resolve credentials through the selected platform driver."""
        return await self._get_platform(platform).authenticate()

    async def _on_room_unavailable(self, room_slug: str, identity: Any | None) -> None:
        """React to DragnCards declining to serve a joined room's state.

        The room channel is the only place a DragnCards credential is checked on
        this path — `POST /api/v1/games` is not behind the authenticated pipeline
        upstream and accepts any token — so a credential the backend has forgotten
        shows up here and nowhere earlier. The realistic cause is the DragnCards
        container being recreated: its Pow credential store lives in the container
        filesystem, so recreating it forgets every issued token while a cached
        entry here would still look fresh.

        A cached credential is therefore evicted, so the next room bootstrap
        derives a new one instead of repeating the failure for the rest of the
        TTL. A credential that was just derived is left alone: evicting it would
        only re-derive the same thing, and the cause is then something other than
        the credential (a room with no server state also produces this push).

        This does not fail the caller. A join that yields no state has always
        produced a session that fetches state on demand, and raising here would
        strand the DragnCards room that was just created — the channel refuses
        every push, including the one that closes a room. Making that path fail
        cleanly is a separate concern from caching the credential.
        """
        logger.warning(
            "DragnCards declined to serve state for room %s on join; "
            "credential_was_cached=%s",
            room_slug,
            bool(identity and identity.cached),
        )
        if identity is not None and identity.cached:
            cache = self._auth_cache or getattr(
                self._get_platform(DRAGNCARDS_PLATFORM), "auth_cache", None
            )
            if cache is not None:
                await cache.invalidate()

    def _build_session(
        self,
        *,
        session_id: str,
        plugin_name: str | None,
        plugin_id: int | None,
        room_slug: str,
        created_at: datetime,
        client: Any = None,
        channel: Any = None,
        driver: GamePlatform | None = None,
        platform: PlatformSlug = DRAGNCARDS_PLATFORM,
        plugin_version: int | None = None,
        initial_state: Any = None,
        ephemeral: bool = False,
        setup: dict[str, Any] | None = None,
    ) -> GameSession:
        session = GameSession(
            session_id=session_id,
            plugin_name=plugin_name,
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            room_slug=room_slug,
            created_at=created_at,
            platform=platform,
            driver=driver,
            client=client,
            channel=channel,
            initial_state=initial_state,
            on_close=lambda: self._remove_session(session_id),
            history_emitter=(
                NullHistoryEmitter() if ephemeral else self._history_emitter
            ),
            ephemeral=ephemeral,
            setup=setup,
        )
        return session

    @staticmethod
    def _setup_metadata(spec: Any) -> dict[str, Any] | None:
        if isinstance(spec, MarvelLcgCreateSpec):
            return {
                "platform": spec.platform,
                "scenario_id": spec.scenario_id,
                "hero_decks": [
                    {"seat": item.seat, "hero_deck_id": item.hero_deck_id}
                    for item in spec.hero_decks
                ],
            }
        if isinstance(spec, DragnCardsCreateSpec):
            return {"platform": spec.platform, "plugin_name": spec.plugin_name}
        return None

    @staticmethod
    def _coerce_create_spec(
        platform: PlatformSlug,
        plugin_name: str,
        plugin_info: dict[str, Any],
        setup: Any,
    ) -> Any:
        if platform == DRAGNCARDS_PLATFORM:
            selected_plugin = getattr(setup, "plugin_name", plugin_name)
            return DragnCardsCreateSpec(
                platform=DRAGNCARDS_PLATFORM,
                plugin_name=selected_plugin,
                plugin_info=plugin_info,
            )
        if setup is None:
            return None
        if isinstance(setup, MarvelLcgCreateSpec):
            return setup
        if getattr(setup, "platform", None) != "marvel-lcg":
            raise SessionError(
                "Platform 'marvel-lcg' cannot use a DragnCards creation specification"
            )
        hero_decks = tuple(
            HeroDeckSelection(
                seat=item.seat,
                hero_deck_id=item.hero_deck_id,
            )
            for item in getattr(setup, "hero_decks", ())
        )
        return MarvelLcgCreateSpec(
            platform=platform,
            scenario_id=setup.scenario_id,
            hero_decks=hero_decks,
        )

    async def _register_session(
        self, session: GameSession, *, persist: bool = True
    ) -> GameSession:
        if persist:
            await self._session_store.put_session(session.to_metadata())

        async with self._lock:
            self._sessions[session.session_id] = session

        return session

    async def _teardown_failed_driver(
        self, driver: GamePlatform, room_slug: str
    ) -> None:
        """Release a driver when bring-up failed before a session was stored."""
        try:
            await driver.teardown(room_slug)
        except Exception as exc:
            logger.warning(
                "Failed to tear down an unregistered %s table: %s",
                driver.slug,
                type(exc).__name__,
            )

    async def _claim_marvel_lease(
        self, driver: GamePlatform, session_id: str
    ) -> tuple[str, str]:
        self._ensure_marvel_lease_capability()
        endpoint = getattr(driver, "http_url", None)
        if not isinstance(endpoint, str) or not endpoint:
            raise SessionError("marvel-lcg singleton endpoint is not configured")
        owner_token = str(uuid.uuid4())
        acquired = await self._session_store.acquire_marvel_lease(
            endpoint,
            session_id,
            owner_token,
            lease_ttl=self._marvel_lease_ttl_seconds,
        )
        if not acquired:
            raise SingletonLeaseConflictError(
                "marvel-lcg supports one active game per engine; another session "
                "currently owns the configured singleton engine"
            )
        # Register the exact ownership tuple and start renewal before any engine
        # table creation or WebSocket connection work. Those calls can outlive a
        # short lease, and a failed creation still owns a real lease that must be
        # released with this token rather than relying on a session record.
        self._marvel_leases[session_id] = (endpoint, owner_token)
        self._start_marvel_lease(session_id, endpoint, owner_token)
        return endpoint, owner_token

    def _ensure_marvel_lease_capability(self) -> None:
        if (
            getattr(self._session_store, "supports_distributed_leases", False)
            is not True
        ):
            raise SessionError(
                "marvel-lcg singleton sessions require the Valkey-backed session "
                "store; the in-memory fallback cannot provide cross-worker fencing"
            )

    def _start_marvel_lease(
        self, session_id: str, endpoint: str, owner_token: str
    ) -> None:
        async def validate() -> bool:
            try:
                owned = await self._session_store.marvel_lease_owned(
                    endpoint, owner_token
                )
            except Exception:
                owned = False
            if not owned:
                await self._mark_marvel_lease_lost(session_id)
            return owned

        async def renew() -> None:
            interval = max(self._marvel_lease_ttl_seconds / 3.0, 0.1)
            try:
                while True:
                    await asyncio.sleep(interval)
                    try:
                        renewed = await self._session_store.renew_marvel_lease(
                            endpoint,
                            owner_token,
                            lease_ttl=self._marvel_lease_ttl_seconds,
                        )
                    except Exception:
                        renewed = False
                    if not renewed:
                        await self._mark_marvel_lease_lost(session_id)
                        return
            except asyncio.CancelledError:
                raise

        self._marvel_lease_validators[session_id] = validate
        self._marvel_lease_tasks[session_id] = asyncio.create_task(renew())

    async def _mark_marvel_lease_lost(self, session_id: str) -> None:
        self._marvel_lease_lost.add(session_id)
        session = self._marvel_lease_sessions.get(session_id)
        if session is None:
            return
        session.mark_degraded("marvel-lcg singleton lease lost")
        try:
            await self._session_store.put_session(session.to_metadata())
        except Exception as exc:
            logger.warning(
                "Failed to persist degraded marvel-lcg session %s: %s",
                session_id,
                type(exc).__name__,
            )

    def _bind_marvel_lease(self, session: GameSession) -> None:
        session_id = session.session_id
        self._marvel_lease_sessions[session_id] = session
        validator = self._marvel_lease_validators.get(session_id)
        setter = getattr(session.driver, "set_lease_validator", None)
        if setter is not None and validator is not None:
            setter(validator)
        if session_id in self._marvel_lease_lost:
            session.mark_degraded("marvel-lcg singleton lease lost")

    async def _release_marvel_lease(self, session_id: str) -> None:
        task = self._marvel_lease_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        lease = self._marvel_leases.pop(session_id, None)
        self._marvel_lease_sessions.pop(session_id, None)
        self._marvel_lease_validators.pop(session_id, None)
        self._marvel_lease_lost.discard(session_id)
        if lease is None:
            return
        endpoint, owner_token = lease
        try:
            await self._session_store.release_marvel_lease(endpoint, owner_token)
        except Exception as exc:
            logger.warning(
                "Failed to release marvel-lcg singleton lease for %s: %s",
                session_id,
                type(exc).__name__,
            )

    async def _restore_session(self, record: dict[str, Any]) -> GameSession:
        with tracer.start_as_current_span(
            "game_service.restore_session",
            attributes={
                "game.platform": record.get("platform", DRAGNCARDS_PLATFORM),
                "game.plugin.name": record.get("plugin_name", ""),
            },
        ):
            platform = record.get("platform", DRAGNCARDS_PLATFORM)
            if platform == "marvel-lcg":
                raise SessionError(
                    "marvel-lcg attachment is unsupported; create a new session "
                    "after discovering setup"
                )
            plugin_name = record.get("plugin_name")
            driver = self._new_platform(platform)
            plugin_info = (
                self._plugin_registry.get(plugin_name)
                if driver.uses_plugin and plugin_name
                else None
            )
            if driver.uses_plugin and plugin_info is None:
                raise SessionError(
                    f"Cannot restore session {record['session_id']!r}: plugin {plugin_name!r} is not available"
                )

            try:
                identity = await driver.authenticate()
                await driver.attach_table(record["room_slug"], identity)
                initial_state = await driver.connect(record["room_slug"], identity)
                session = self._build_session(
                    session_id=record["session_id"],
                    plugin_name=plugin_name if driver.uses_plugin else None,
                    plugin_id=(plugin_info or {}).get("id"),
                    room_slug=record["room_slug"],
                    created_at=datetime.fromisoformat(record["created_at"]),
                    driver=driver,
                    platform=platform,
                    plugin_version=(plugin_info or {}).get("version"),
                    initial_state=initial_state,
                    ephemeral=bool(record.get("ephemeral", False)),
                    setup=record.get("setup"),
                )
            except Exception:
                await self._teardown_failed_driver(driver, record["room_slug"])
                raise
            await self._register_session(session, persist=False)

            logger.info(
                "Restored session %s from coordination store", session.session_id
            )
            return session

    async def _read_state_for_seating(self, session: GameSession) -> Any | None:
        """Room state for a seating decision, or ``None`` when it cannot be read.

        Seating is always best-effort: a room whose state cannot be fetched is
        still a usable room, and refusing to create or configure a session over
        an unreadable seat map would be a worse failure than an unnamed seat.
        """
        try:
            state = await session.get_state()
        except SessionError as exc:
            logger.warning(
                "seating: session_id=%s state unavailable: %s",
                session.session_id,
                exc,
            )
            return None
        if not isinstance(state, dict):
            logger.warning(
                "seating: session_id=%s invalid state payload", session.session_id
            )
            return None
        return state

    async def _auto_seat(self, session: GameSession, user_id: int) -> None:
        """Seat this service in the first vacant seat of a freshly opened room.

        Only one seat, because at creation and attach time the room's player
        count is not yet known. The seats a multi-player game needs are claimed
        later, by :meth:`claim_seats`, when the count is set.
        """
        state = await self._read_state_for_seating(session)
        if state is None:
            return

        occupants = seat_occupants(state)
        if user_id in occupants.values():
            logger.info(
                "auto_seat: session_id=%s user already seated", session.session_id
            )
            return

        for player_n, occupant in occupants.items():
            if occupant is not None:
                continue
            try:
                await session.set_seat(player_id=player_n, user_id=user_id)
                logger.info(
                    "auto_seat: session_id=%s assigned user=%s to %s",
                    session.session_id,
                    user_id,
                    player_n,
                )
                return
            except Exception as exc:
                logger.warning(
                    "auto_seat: session_id=%s seat %s failed (%s)",
                    session.session_id,
                    player_n,
                    type(exc).__name__,
                )

        logger.info("auto_seat: session_id=%s no vacant seats", session.session_id)

    async def claim_seats(self, session: GameSession, num_players: int) -> list[str]:
        """Occupy every vacant seat this room's player count implies.

        A seat needs an occupant for the game *log* to be complete, not just for
        display: Marvel Champions logs each seat's draw through that seat's
        recorded alias and writes no line at all when the alias is absent, so an
        unclaimed seat's draws never reach history or evaluation.

        Seats held by another user are left alone — that occupant is a
        participant this service did not put there. Failures are logged and
        swallowed: a missing log alias must never block setting up a game.

        Returns the seats actually claimed. Assumes the caller already holds the
        session operation lock.
        """
        state = await self._read_state_for_seating(session)
        if state is None:
            return []

        user_id = await self._own_user_id(session.platform)
        if user_id is None:
            logger.warning(
                "claim_seats: session_id=%s could not resolve own user id",
                session.session_id,
            )
            return []

        claimed: list[str] = []
        for player_n in seats_to_claim(state, num_players):
            try:
                await session.claim_seat(player_id=player_n, user_id=user_id)
            except Exception as exc:
                logger.warning(
                    "claim_seats: session_id=%s seat %s failed (%s)",
                    session.session_id,
                    player_n,
                    type(exc).__name__,
                )
                continue
            claimed.append(player_n)

        logger.info(
            "claim_seats: session_id=%s num_players=%s claimed=%s",
            session.session_id,
            num_players,
            claimed,
        )
        return claimed

    async def _own_user_id(self, platform: str = DRAGNCARDS_PLATFORM) -> int | None:
        """This service's platform identity, resolved through its driver.

        Deliberately not inferred from whoever already occupies a seat in the
        room: a human may be sitting there, and claiming the remaining seats for
        *them* would be worse than not claiming at all. The id comes from the
        same platform credential every room-bootstrapping path uses, so asking for
        it costs a login round-trip only when nothing is cached yet. Platforms
        without a numeric identity simply decline automatic seat claiming.
        """
        try:
            identity = await self._credentials(platform)
            user_id = getattr(identity, "user_id", None)
            return user_id if isinstance(user_id, int) else None
        except Exception as exc:
            logger.warning(
                "Could not resolve own DragnCards user id (%s)", type(exc).__name__
            )
            return None

    async def create_session(
        self,
        plugin_name: str = "marvel-champions",
        *,
        platform: PlatformSlug = DRAGNCARDS_PLATFORM,
        ephemeral: bool = False,
        setup: Any = None,
    ) -> GameSession:
        with tracer.start_as_current_span(
            "game_service.create_session",
            attributes={
                "game.platform": platform,
                "game.plugin.name": plugin_name,
                "game.session.ephemeral": ephemeral,
            },
        ):
            driver = self._new_platform(platform)
            selected_plugin_name = getattr(setup, "plugin_name", plugin_name)
            plugin_info = (
                self._get_plugin_info(selected_plugin_name)
                if driver.uses_plugin
                else {}
            )
            room_slug = ""
            session_id = str(uuid.uuid4())
            marvel_lease: tuple[str, str] | None = None
            try:
                if platform == "marvel-lcg":
                    self._ensure_marvel_lease_capability()
                identity = await driver.authenticate()
                requested_spec = self._coerce_create_spec(
                    platform, selected_plugin_name, plugin_info, setup
                )
                resolved_spec = await driver.resolve_create_spec(requested_spec)
                if platform == "marvel-lcg":
                    # Resolve the live catalog before claiming so the bounded lease
                    # covers table creation and connection, not an unbounded read.
                    marvel_lease = await self._claim_marvel_lease(driver, session_id)
                room = await driver.create_table(identity, resolved_spec)
                room_slug = room["slug"]
                logger.info("Created %s room %s", platform, room_slug)
                initial_state = await driver.connect(room_slug, identity)

                session = self._build_session(
                    session_id=session_id,
                    plugin_name=selected_plugin_name if driver.uses_plugin else None,
                    plugin_id=plugin_info.get("id"),
                    room_slug=room_slug,
                    created_at=datetime.now(timezone.utc),
                    driver=driver,
                    platform=platform,
                    plugin_version=plugin_info.get("version"),
                    initial_state=initial_state,
                    ephemeral=ephemeral,
                    setup=self._setup_metadata(resolved_spec),
                )
                if marvel_lease is not None:
                    self._bind_marvel_lease(session)
                await self._register_session(session)
            except Exception:
                await self._teardown_failed_driver(driver, room_slug)
                if marvel_lease is not None:
                    await self._release_marvel_lease(session_id)
                raise
            user_id = getattr(identity, "user_id", None)
            if isinstance(user_id, int):
                await self._auto_seat(session, user_id)

            if marvel_lease is not None:
                validator = self._marvel_lease_validators.get(session_id)
                if validator is not None and not await validator():
                    logger.warning(
                        "Marvel session %s became degraded before creation returned",
                        session_id,
                    )

            logger.info("Session %s created (room=%s)", session_id, room_slug)
            return session

    async def attach_session(
        self,
        plugin_name: str = "marvel-champions",
        room_slug: str = "",
        *,
        platform: PlatformSlug = DRAGNCARDS_PLATFORM,
    ) -> GameSession:
        if platform == "marvel-lcg":
            raise SessionError(
                "marvel-lcg attachment is unsupported because the engine has no "
                "stable external room identifier; create a new session instead"
            )
        driver = self._new_platform(platform)
        plugin_info = self._get_plugin_info(plugin_name) if driver.uses_plugin else {}
        try:
            identity = await driver.authenticate()
            await driver.attach_table(room_slug, identity)
            initial_state = await driver.connect(room_slug, identity)

            session_id = str(uuid.uuid4())
            session = self._build_session(
                session_id=session_id,
                plugin_name=plugin_name if driver.uses_plugin else None,
                plugin_id=plugin_info.get("id"),
                room_slug=room_slug,
                created_at=datetime.now(timezone.utc),
                driver=driver,
                platform=platform,
                plugin_version=plugin_info.get("version"),
                initial_state=initial_state,
            )
            await self._register_session(session)
        except Exception:
            # Attaching never owns the existing table, so only detach the client;
            # do not ask the platform to destroy somebody else's game.
            await self._teardown_failed_driver(driver, room_slug)
            raise
        user_id = getattr(identity, "user_id", None)
        if isinstance(user_id, int):
            await self._auto_seat(session, user_id)

        logger.info("Session %s attached to existing room %s", session_id, room_slug)
        return session

    @staticmethod
    def _as_canonical_uuid(value: str) -> str | None:
        """Return ``value`` as a canonical UUID string, or ``None`` if it is not one.

        A valid but non-canonical UUID (e.g. uppercase or braced) is normalized so
        that it still matches the canonical id stored on the session.
        """
        try:
            return str(uuid.UUID(str(value)))
        except ValueError, AttributeError, TypeError:
            return None

    async def resolve_session_id(self, identifier: str) -> str:
        """Resolve a session UUID *or* a human-readable room slug to a session id.

        Every session-identifying path (state reads, mutations, and deletes) funnels
        through here, so an operator or an agent can work in terms of the readable
        DragnCards room slug (`lively-fog-1234`) instead of the opaque UUID. A
        well-formed UUID is returned in canonical form without a store round-trip, so
        an already-removed session still resolves and delete stays idempotent;
        anything else is treated as a room slug and resolved through the session pool
        or the session store's slug index.

        Raises ``SessionNotFoundError`` when the value is neither a UUID nor a known
        room slug, and ``AmbiguousSessionIdentifierError`` when the slug matches more
        than one live session.
        """
        canonical = self._as_canonical_uuid(identifier)
        if canonical is not None:
            return canonical
        return await self._resolve_room_slug(identifier)

    async def _resolve_room_slug(self, room_slug: str) -> str:
        """Resolve a room slug to a session id via the pool, then the store index."""
        # In-pool scan first: it is also the only place duplicate slugs are
        # detectable, because `attach_session` may create more than one session for
        # the same DragnCards room and the store's slug index is last-writer-wins.
        live_matches = sorted(
            {
                session.session_id
                for session in self._sessions.values()
                if session.room_slug == room_slug
            }
        )
        if len(live_matches) > 1:
            raise AmbiguousSessionIdentifierError(
                f"Room slug {room_slug!r} matches {len(live_matches)} sessions "
                f"({', '.join(live_matches)}); use the session's `session_id` instead."
            )
        if live_matches:
            return live_matches[0]

        session_id = await self._session_store.get_session_id_by_slug(room_slug)
        if session_id is not None:
            if await self._session_store.get_session(session_id) is not None:
                return session_id
        raise SessionNotFoundError(
            f"{room_slug!r} is neither a session id nor a known room slug"
        )

    async def lookup_session_by_slug(self, room_slug: str) -> dict[str, Any]:
        """Resolve a human-readable ``room_slug`` to its session metadata.

        A convenience read: every session endpoint already accepts a room slug in
        the ``session_id`` position, so this is only needed when the caller wants the
        full session metadata (including the canonical UUID ``session_id``) rather
        than acting on the session. Raises ``SessionNotFoundError`` when the slug is
        unknown.
        """
        session_id = await self._resolve_room_slug(room_slug)
        session = self._sessions.get(session_id)
        if session is not None:
            return session.to_metadata()
        record = await self._session_store.get_session(session_id)
        if record is None:
            raise SessionNotFoundError(f"Session for room slug {room_slug!r} not found")
        return dict(record)

    async def get_session(self, session_id: str) -> GameSession:
        session_id = await self.resolve_session_id(session_id)
        session = self._sessions.get(session_id)
        if session is None:
            record = await self._session_store.get_session(session_id)
            if record is None:
                raise SessionNotFoundError(f"Session {session_id!r} not found")
            session = await self._restore_session(record)
        return session

    @asynccontextmanager
    async def session_operation_lock(
        self,
        session_id: str,
        *,
        wait_timeout: float = 5.0,
        lease_ttl: float = 30.0,
    ):
        # Resolve first so a slug-addressed and a UUID-addressed operation on the
        # same session contend for the same lock key.
        session_id = await self.resolve_session_id(session_id)
        owner_token = str(uuid.uuid4())
        acquired = await self._session_store.acquire_session_lock(
            session_id=session_id,
            owner_token=owner_token,
            lease_ttl=lease_ttl,
            wait_timeout=wait_timeout,
        )
        if not acquired:
            raise SessionLockedError(
                f"Session {session_id!r} is busy; could not acquire operation lock within {wait_timeout:.1f}s"
            )
        try:
            yield
        finally:
            try:
                await self._session_store.release_session_lock(session_id, owner_token)
            except Exception as exc:
                logger.warning(
                    "Failed to release operation lock for session %s: %s",
                    session_id,
                    exc,
                )

    async def _remove_session(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)
        await self._release_marvel_lease(session_id)
        await self._session_store.delete_session(session_id)
        logger.info("Session %s removed from pool (room closed)", session_id)

    async def delete_session(self, session_id: str) -> None:
        session_id = await self.resolve_session_id(session_id)
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is None:
            raise SessionNotFoundError(f"Session {session_id!r} not found")
        if session.ephemeral:
            # An ephemeral reconstruction owns its DragnCards room outright (it
            # was created solely to view a past moment), so tearing the session
            # down must close the room too — otherwise every "board at this
            # event" view leaves a room behind forever. The room event has to be
            # pushed while the channel is still joined, hence before the leave
            # below. Best-effort: a failure here must not block the teardown.
            try:
                await session.close_room()
            except Exception as exc:
                logger.warning(
                    "Error closing room %s for ephemeral session %s: %s",
                    session.room_slug,
                    session_id,
                    exc,
                )
        try:
            await session.driver.teardown(session.room_slug)
        except Exception as exc:
            logger.warning("Error tearing down session %s: %s", session_id, exc)
        await self._release_marvel_lease(session_id)
        await self._session_store.delete_session(session_id)
        logger.info("Session %s deleted", session_id)

    async def load_prebuilt_deck(
        self, session_id: str, deck_id: str, player_n: str = "player1"
    ) -> Any:
        player_n = normalise_seat_id(player_n)
        async with self.session_operation_lock(session_id):
            session = await self.get_session(session_id)
            if (
                session.driver.move_surface != "typed_actions"
                or session.plugin_name is None
            ):
                raise SessionError(
                    "Prebuilt decks are only available on the DragnCards platform"
                )
            deck = load_prebuilt_deck(deck_id, session.plugin_name)
            if deck is None:
                raise SessionError(
                    f"Prebuilt deck {deck_id!r} not found for plugin {session.plugin_name!r}"
                )
            before_state = await session.get_state()
            await self._ensure_seat_has_layout(session, player_n, before_state)
            result = await session.load_prebuilt_deck(
                deck.get("deck_id", deck_id), player_n=player_n
            )

            await asyncio.sleep(0.5)
            for _ in range(10):
                after_state = await session.get_state()
                if isinstance(after_state, dict):
                    game = after_state.get("game")
                    if isinstance(game, dict) and isinstance(
                        game.get("messages"), list
                    ):
                        messages = game["messages"]
                        # The platform owns the upstream message vocabulary and
                        # raises the same bad-state exception as normal actions.
                        session.check_bad_game_state(after_state)
                        if game.get("loadedCardIds") or game.get("loadCardsHistory"):
                            return result
                await asyncio.sleep(0.2)

            return result

    async def _ensure_seat_has_layout(
        self, session: GameSession, player_n: str, state: Any
    ) -> None:
        """Bump the room's player count before a deck load targets an uncovered seat.

        DragnCards renders only the groups that have a region in the room's
        active layout. Loading a hero deck for ``player2`` while the room is
        still laid out for one player puts that hero's cards in groups with no
        region: they exist in the game state (and are visible over MCP) but
        never appear on the table. The human flow avoids this by setting the
        player count — which switches the layout — before loading decks; this
        replicates that order for automated callers that get it wrong (DRA-52).
        """
        if not isinstance(state, dict):
            return
        game = state.get("game")
        if not isinstance(game, dict):
            return
        seat_number = _seat_number(player_n)
        if seat_number is None or seat_number <= 1:
            # Seat 1 is covered by every layout; a fresh room starts at 1 player.
            return
        raw_count = game.get("numPlayers")
        try:
            current_players = int(raw_count) if raw_count is not None else 1
        except TypeError, ValueError:
            current_players = 1
        if current_players >= seat_number:
            return
        layout_id = _layout_id_for_player_count(session.plugin_name, seat_number)
        await session.set_player_count(num_players=seat_number, layout_id=layout_id)

    async def list_sessions(self) -> list[dict]:
        records = await self._session_store.list_sessions()
        return [dict(record) for record in records]

    def platform_driver(self, platform: str) -> GamePlatform:
        """Return the configured platform template for read-only catalog calls."""
        return self._get_platform(platform)

    async def list_setup_catalog(self, platform: PlatformSlug) -> dict[str, Any]:
        """Return the selected driver's backend-neutral setup catalog."""
        driver = self.platform_driver(platform)
        await driver.authenticate()
        return await driver.setup_catalog()

    async def close_all(self) -> None:
        session_ids = list(self._sessions.keys())
        for sid in session_ids:
            try:
                await self.delete_session(sid)
            except Exception as exc:
                logger.warning("Error closing session %s on shutdown: %s", sid, exc)

    # ------------------------------------------------------------------
    # Ephemeral reconstruction reaper
    # ------------------------------------------------------------------
    #
    # Ephemeral reconstruction sessions are view-only branches created for the
    # dashboard "open board at this event" feature. Client teardown
    # (DELETE /games/{id}) is the fast path, but it is best-effort only: a lost
    # network connection, tab crash, or power loss can leave the session and its
    # DragnCards room orphaned. This background reaper deletes ephemeral sessions
    # (and their rooms) once they are older than the configured TTL, so a crashed
    # client can never leak one. Non-ephemeral sessions are never touched. The
    # ephemeral tag and created_at live in the session store (no in-memory-only
    # durable state), so reaping is correct across service instances and restarts.

    async def reap_expired_ephemeral_sessions(self) -> int:
        """Delete ephemeral sessions older than the configured TTL.

        Returns the number of sessions reaped. Reads candidates from the session
        store (the durable source of the ``ephemeral`` tag + ``created_at``), so
        a session that was never loaded into this process's pool is still
        reclaimed. Idempotent: a record already removed (e.g. by an explicit
        client teardown) is simply skipped.
        """
        now = datetime.now(timezone.utc)
        ttl = self._ephemeral_session_ttl_seconds
        try:
            records = await self._session_store.list_sessions()
        except Exception as exc:  # best-effort: never crash the reaper loop
            logger.warning("ephemeral reaper: failed to list sessions: %s", exc)
            return 0

        reaped = 0
        for record in records:
            if not record.get("ephemeral"):
                continue
            created_raw = record.get("created_at")
            if not isinstance(created_raw, str):
                continue
            try:
                created_at = datetime.fromisoformat(created_raw)
            except ValueError:
                continue
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age = (now - created_at).total_seconds()
            if age < ttl:
                continue
            session_id = record["session_id"]
            if await self._reap_ephemeral_session(session_id):
                reaped += 1
        if reaped:
            logger.info("ephemeral reaper: reclaimed %d expired session(s)", reaped)
        return reaped

    async def _reap_ephemeral_session(self, session_id: str) -> bool:
        """Delete a single ephemeral session + its room. Best-effort, idempotent."""
        try:
            # Reuse the existing session-delete path (leave channel + disconnect
            # + remove store record). This mirrors the client fast path exactly.
            await self.delete_session(session_id)
            logger.info("ephemeral reaper: reclaimed session %s", session_id)
            return True
        except SessionNotFoundError:
            # Not in the pool: the room may never have been loaded by this
            # instance, or it was already removed. Ensure the durable record is
            # gone so the room is not left tracked, then treat as reclaimed.
            try:
                await self._session_store.delete_session(session_id)
            except Exception as exc:  # best-effort
                logger.warning(
                    "ephemeral reaper: failed to delete store record for %s: %s",
                    session_id,
                    exc,
                )
                return False
            logger.info(
                "ephemeral reaper: removed stale store record for %s", session_id
            )
            return True
        except Exception as exc:  # best-effort: never crash the reaper loop
            logger.warning(
                "ephemeral reaper: failed to reap session %s: %s", session_id, exc
            )
            return False

    async def _ephemeral_reaper_loop(self) -> None:
        """Periodically reap expired ephemeral sessions until cancelled."""
        interval = self._ephemeral_reaper_interval_seconds
        logger.info(
            "Started ephemeral session reaper (ttl=%.0fs interval=%.0fs)",
            self._ephemeral_session_ttl_seconds,
            interval,
        )
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await self.reap_expired_ephemeral_sessions()
                except Exception as exc:  # best-effort: keep the loop alive
                    logger.warning("ephemeral reaper: cycle failed: %s", exc)
        except asyncio.CancelledError:
            logger.info("Ephemeral session reaper stopped")
            raise

    def start_ephemeral_reaper(self) -> None:
        """Start the background reaper task (idempotent)."""
        if self._reaper_task is not None and not self._reaper_task.done():
            return
        self._reaper_task = asyncio.create_task(self._ephemeral_reaper_loop())

    async def stop_ephemeral_reaper(self) -> None:
        """Stop the background reaper task if running."""
        task = self._reaper_task
        if task is None:
            return
        self._reaper_task = None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("ephemeral reaper: error during shutdown: %s", exc)
