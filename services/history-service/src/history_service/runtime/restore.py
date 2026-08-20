from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from history_service.integrations.game_service import BranchSession, GameServiceClient
from history_service.integrations.orchestrator import OrchestratorClient
from history_service.schemas.envelope import (
    PLATFORM_DRAGNCARDS,
    Platform,
    StoredEvent,
    StoredSnapshot,
)
from history_service.storage.repository import Repository
from history_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

RestoreMode = Literal["new", "in_place"]


class RestoreError(Exception):
    """Raised for client-correctable restore failures (e.g. out-of-range seq)."""


@dataclass(frozen=True)
class _RestoreBase:
    """The full-state document a restore starts from, and the seq it holds.

    Two kinds of stored record embed a complete board: a periodic snapshot, and
    any ``game-service`` game-state event (whose payload carries the whole
    state). State events are dense — one per game action — while snapshots are
    sparse, so the nearest state event is usually at or just below the target
    and needs little or no forward replay. Whichever is more recent wins.
    """

    document: dict[str, Any]
    # Never None: a snapshot always has a ``snapshot_at_seq`` and an event always
    # has a ``seq``. Keeping it non-optional matters because the replay range's
    # lower bound is derived from it, and a nullable seq invites an ``or 0``
    # fallback that silently means "replay the entire log from the start".
    seq: int


@dataclass
class RestoreResult:
    game_id: str
    target_seq: int
    mode: RestoreMode
    game_session_id: str
    orchestrator_session_id: str | None
    snapshot_at_seq: int | None
    platform: Platform = PLATFORM_DRAGNCARDS
    replayed_event_seqs: list[int] = field(default_factory=list)
    status_verified: bool | None = None
    divergence: str | None = None
    # The DragnCards room the restored state lives in. Populated for a branch
    # ("new") restore, whose whole point is a room the caller then has to find.
    room_slug: str | None = None
    # Whether the agent-context layer was rebuilt, and why not when it was not.
    # A game with no agent session to resume is a normal state, not a failure of
    # the game-state restore, so it is reported rather than raised.
    agent_context_restored: bool = False
    agent_context_note: str | None = None


class RestoreService:
    """Reconstructs a game to a past moment across game-state + agent layers."""

    def __init__(
        self,
        *,
        repository: Repository,
        game_service: GameServiceClient,
        orchestrator: OrchestratorClient,
    ):
        self._repository = repository
        self._game_service = game_service
        self._orchestrator = orchestrator

    async def restore(
        self,
        game_id: str,
        *,
        target_seq: int,
        mode: RestoreMode = "new",
        ephemeral: bool = False,
        reuse_session_id: str | None = None,
        platform: Platform | None = PLATFORM_DRAGNCARDS,
    ) -> RestoreResult:
        """Traced entry point; the workflow itself is :meth:`_restore`.

        Restore is a multi-step, repo-specific workflow (snapshot load, forward
        replay, agent-context restore, verify) that generic library
        instrumentation cannot explain, so it gets one span covering the whole
        thing. Only identifiers and mode flags are attached — never the replayed
        events or the restored state.
        """
        if platform is None:
            matching = [
                summary
                for summary in await self._repository.list_games()
                if summary.game_id == game_id
            ]
            platform = (
                matching[0].platform if len(matching) == 1 else PLATFORM_DRAGNCARDS
            )
        with tracer.start_as_current_span(
            "history.restore",
            attributes={
                "game.id": game_id,
                "history.target_seq": target_seq,
                "history.restore_mode": mode,
                "history.ephemeral": ephemeral,
                # Whether a session to reuse was offered, not which one: the id is
                # already the span's `game.id` when it is honoured, and a flag is
                # what a trace needs to tell a fast re-point from a fresh build.
                "history.reuse_offered": reuse_session_id is not None,
                "history.platform": platform,
            },
        ):
            return await self._restore(
                game_id,
                target_seq=target_seq,
                mode=mode,
                ephemeral=ephemeral,
                reuse_session_id=reuse_session_id,
                platform=platform,
            )

    async def _restore(
        self,
        game_id: str,
        *,
        target_seq: int,
        mode: RestoreMode,
        ephemeral: bool,
        reuse_session_id: str | None = None,
        platform: Platform = PLATFORM_DRAGNCARDS,
    ) -> RestoreResult:
        if platform is None:
            matching = [
                summary
                for summary in await self._repository.list_games()
                if summary.game_id == game_id
            ]
            platform = (
                matching[0].platform if len(matching) == 1 else PLATFORM_DRAGNCARDS
            )
        # 1. Validate target_seq is in range BEFORE mutating anything.
        latest_seq = await self._repository.get_latest_seq(game_id, platform)
        if latest_seq is None or target_seq < 1 or target_seq > latest_seq:
            raise RestoreError(
                f"target_seq {target_seq} is out of range for game {game_id!r} "
                f"(valid range: 1..{latest_seq if latest_seq else 0})"
            )

        # 2. Resolve the nearest snapshot at/<= target up front: it is one of the
        #    two possible game-state bases and a source of the ``plugin_name``
        #    needed to materialize a fresh branch session.
        snapshot = await self._repository.get_latest_snapshot_at_or_before(
            game_id, target_seq, platform
        )

        # 3. Resolve the full-state base, for BOTH modes.
        #
        # The slug is only *needed* to synthesize a load document from a state
        # event; a game recording none anywhere simply falls back to its
        # snapshot. A branch restore additionally cannot materialize a room
        # without it, and that requirement is enforced where the room is created
        # rather than here — so the value stays narrowable instead of being cast.
        plugin_name = await self._resolve_plugin_name(game_id, snapshot, platform)
        state_event = None
        if plugin_name:
            state_event = await self._repository.get_latest_state_event_at_or_before(
                game_id, target_seq, platform
            )
        base = _choose_base(snapshot, state_event, plugin_name)

        # 4. Determine the target game-service session.
        #    - "in_place": rewind the existing live session (same game_id).
        #    - "new": create a fresh real DragnCards session, leaving the
        #      original timeline intact, then load + replay into it.
        #
        # ``created_new_session`` tracks whether we materialized a real
        # game-service room for this restore so we can roll it back if a later
        # step fails (a half-built branch must not be left behind).
        created_new_session = False
        room_slug: str | None = None
        if mode == "in_place":
            # An in-place rewind MUST start from a clean full-state base before
            # forward replay, otherwise replaying (low_exclusive, target] on top
            # of the un-rewound live state double-applies every event. Either
            # kind of base establishes that clean base; without one there is no
            # safe way to rewind in place, so reject rather than corrupt the live
            # session.
            if base is None:
                raise RestoreError(
                    f"cannot rewind game {game_id!r} in place to seq {target_seq}: "
                    "no snapshot and no recorded game state at or before the "
                    "target exists to establish a clean base (restore into a new "
                    "branchable session instead)"
                )
            game_session_id = game_id
            await self._assert_target_platform(game_session_id, platform)
        elif reuse_session_id is not None and ephemeral and base is not None:
            # Re-point a session the caller already owns instead of building a
            # second room for the same game. Creating one is several sequential
            # DragnCards round trips plus a channel join and a plugin load; loading
            # a base into an open room is a single state load.
            #
            # Two conditions gate this, and neither is an optimisation detail.
            #
            # ``base is not None`` is what makes it correct. Loading a base issues
            # DragnCards ``set_game``, which returns the supplied document outright
            # rather than merging into the room's existing game, so the reused
            # session ends in exactly the target state and nothing from the moment
            # it previously held survives. The no-base path has no such guarantee —
            # it replays forward from seq 1 onto whatever the session already holds
            # — so it falls through to creating a fresh session below rather than
            # being reasoned about case by case.
            #
            # ``ephemeral`` is what keeps it aimed at the flow it exists for. Reuse
            # overwrites a session named by the caller rather than one this restore
            # created, and an ephemeral reconstruction is by definition a throwaway
            # the caller built to look at. A kept branch restore is meant to own the
            # room it produces, so it gets a fresh one; without this condition the
            # field would be a way to overwrite an unrelated live session with a
            # different game's board.
            #
            # ``created_new_session`` stays false: the caller owns this session, so
            # a failed restore must not delete it. ``room_slug`` stays None because
            # no room was created; the caller already knows the room it handed over.
            game_session_id = reuse_session_id
            logger.info(
                "Restoring game %s to seq %s into caller-supplied session %s",
                game_id,
                target_seq,
                game_session_id,
            )
            await self._assert_target_platform(game_session_id, platform)
        else:
            if plugin_name is None:
                raise RestoreError(
                    "cannot create a new branch session: no plugin_name is "
                    "recorded for this game (no snapshot and no game-state event "
                    "carries one)"
                )
            # An ephemeral branch is a non-emitting, server-reaped reconstruction
            # for viewing only; pass the flag through so the game-service tags the
            # session and never emits history for it.
            branch = await self._create_branch_session(
                plugin_name, ephemeral=ephemeral, platform=platform
            )
            game_session_id = branch.session_id
            room_slug = branch.room_slug
            created_new_session = True

        # 5. Apply the restore: load the base, replay forward, restore agent
        #    context, then verify. Any failure mid-apply leaves a partial state;
        #    surface it as a RestoreError (the router maps it to a clean 4xx
        #    instead of an unhandled 500) and, for a freshly created branch,
        #    best-effort delete the room we created so it is not orphaned.
        try:
            return await self._apply_restore(
                game_id=game_id,
                game_session_id=game_session_id,
                target_seq=target_seq,
                mode=mode,
                base=base,
                ephemeral=ephemeral,
                room_slug=room_slug,
                platform=platform,
            )
        except RestoreError:
            if created_new_session:
                await self._cleanup_branch_session(game_session_id)
            raise
        except Exception as exc:  # noqa: BLE001 - convert to a reported failure
            if created_new_session:
                await self._cleanup_branch_session(game_session_id)
            raise RestoreError(
                f"restore of game {game_id!r} to seq {target_seq} failed during "
                f"replay/restore: {exc}"
            ) from exc

    async def _apply_restore(
        self,
        *,
        game_id: str,
        game_session_id: str,
        target_seq: int,
        mode: RestoreMode,
        base: _RestoreBase | None,
        ephemeral: bool = False,
        room_slug: str | None = None,
        platform: Platform = PLATFORM_DRAGNCARDS,
    ) -> RestoreResult:
        # Game-state layer: load the densest available base at/<= target, then
        # forward-replay any mutating actions after it.
        #
        # Loading a full-state base rather than replaying from the start of the
        # log is not an optimisation, it is a correctness requirement: replay only
        # covers actions recorded as replayable generic actions, and setup actions
        # like deck loading are NOT, so replaying from seq 0 yields an empty
        # board.
        if base is not None:
            await self._load_base(game_session_id, base.document, mode=mode)
            low_exclusive = snapshot_at_seq = base.seq
        else:
            # No full-state base available: replay from the start of the log.
            # (in_place restore without a base is rejected before reaching here,
            # so this path only applies to mode="new".)
            low_exclusive = 0
            snapshot_at_seq = None

        # Only ``game-service`` events are ever replayed as mutations, and only
        # they carry the recorded status the verification step compares against,
        # so the range is filtered in the database rather than fetched whole and
        # skipped in Python. On the common path the base IS the last game-service
        # event at or before the target, so this range is empty and the read costs
        # nothing — where unfiltered it fetched and parsed every intervening agent
        # payload (219,476 bytes measured on a 124-event game) only to skip them.
        replay_events = await self._repository.get_events_in_range(
            game_id,
            low_exclusive=low_exclusive,
            high_inclusive=target_seq,
            actor="game-service",
            platform=platform,
        )
        replayed_seqs: list[int] = []
        for event in replay_events:
            if not _is_mutating_event(event):
                continue
            await self._game_service.replay_action(game_session_id, event.payload)
            replayed_seqs.append(event.seq)

        # Agent-context layer: latest agent event at/<= target -> orchestrator.
        # An ephemeral reconstruction is a view-only board, so it does not need
        # (and must not create) an orchestrator agent session: skip this layer.
        if ephemeral:
            orchestrator_session_id = None
            agent_note: str | None = (
                "View-only reconstruction: no agent session was created for it."
            )
        else:
            orchestrator_session_id, agent_note = await self._restore_agent_context(
                game_id, game_session_id, target_seq, mode, platform
            )

        # Verify post-restore status against the stored event, if available.
        status_verified, divergence = await self._verify_status(
            game_session_id, replay_events, target_seq
        )

        return RestoreResult(
            game_id=game_id,
            platform=platform,
            target_seq=target_seq,
            mode=mode,
            game_session_id=game_session_id,
            orchestrator_session_id=orchestrator_session_id,
            snapshot_at_seq=snapshot_at_seq,
            replayed_event_seqs=replayed_seqs,
            status_verified=status_verified,
            divergence=divergence,
            room_slug=room_slug,
            agent_context_restored=orchestrator_session_id is not None,
            agent_context_note=agent_note,
        )

    async def _load_base(
        self, game_session_id: str, document: dict[str, Any], *, mode: RestoreMode
    ) -> None:
        """Load the full-state base document into the target session.

        This is the first mutating call of a restore, so a failure here has
        changed nothing yet. For an in-place rewind a ``404`` means the live
        DragnCards session named by the ``game_id`` no longer exists — the room
        was deleted, or reaped — and there is therefore nothing to overwrite.
        That is a normal consequence of browsing an old game's history, so it is
        reported as an actionable message naming the alternative rather than
        surfaced as a raw upstream ``404`` that reads like a missing route.
        """
        try:
            await self._game_service.load_snapshot(game_session_id, document)
        except httpx.HTTPStatusError as exc:
            if mode == "in_place" and exc.response.status_code == 404:
                raise RestoreError(
                    f"cannot rewind game {game_session_id!r} in place: its live "
                    "game-service session no longer exists, so there is no game "
                    "state to overwrite. Restore into a new branchable session "
                    "instead."
                ) from exc
            raise

    async def _cleanup_branch_session(self, game_session_id: str) -> None:
        """Best-effort deletion of a branch room created for a failed restore."""
        try:
            await self._game_service.delete_session(game_session_id)
            logger.info(
                "Cleaned up branch session %s after failed restore", game_session_id
            )
        except Exception:  # noqa: BLE001 - cleanup must not mask the real error
            logger.warning(
                "Failed to clean up branch session %s after failed restore",
                game_session_id,
                exc_info=True,
            )

    async def _assert_target_platform(
        self, game_session_id: str, platform: Platform
    ) -> None:
        """Reject a known cross-platform target before loading any state.

        The optional capability keeps restores compatible with pre-platform
        game-service deployments, whose only possible platform was DragnCards.
        """
        resolver = getattr(self._game_service, "get_session_platform", None)
        if resolver is None:
            if platform != PLATFORM_DRAGNCARDS:
                raise RestoreError(
                    "game-service does not advertise session platforms; "
                    f"cannot safely restore {platform!r} history"
                )
            return
        target_platform = await resolver(game_session_id)
        if target_platform != platform:
            raise RestoreError(
                f"cannot restore {platform!r} history into {target_platform!r} session"
            )

    async def _resolve_plugin_name(
        self, game_id: str, snapshot: StoredSnapshot | None, platform: Platform
    ) -> str | None:
        """Resolve the plugin slug for this game, or None when none is recorded.

        The slug is recorded both in snapshot documents and on every game-state
        event payload. Prefer the nearest snapshot, then the earliest snapshot,
        then the earliest game-state event — so a restore works even when no
        snapshot has been taken yet (short games).

        Returning None is a valid outcome, not an error: an in-place rewind owns
        its room already and uses the slug solely to synthesize a load document
        from a state event, so it falls back to its snapshot. Only a branch
        restore truly requires the slug, and it raises at the point it creates the
        room.

        The snapshot fallback is read with ``limit=1``. It only ever consumed the
        first row, and every snapshot row carries a full board document (~245 KB
        measured), so an unbounded read transferred and JSON-parsed every
        snapshot of the game to extract one short string.
        """
        plugin_name = _plugin_name_from_snapshot(snapshot)
        if not plugin_name:
            all_snapshots = await self._repository.list_snapshots(
                game_id, platform=platform, limit=1
            )
            plugin_name = _plugin_name_from_snapshot(
                all_snapshots[0] if all_snapshots else None
            )
        if not plugin_name:
            earliest = await self._repository.get_earliest_state_event(
                game_id, platform
            )
            if earliest is not None:
                candidate = earliest.payload.get("plugin_name")
                if isinstance(candidate, str) and candidate:
                    plugin_name = candidate
        return plugin_name or None

    async def _create_branch_session(
        self,
        plugin_name: str,
        *,
        ephemeral: bool = False,
        platform: Platform = PLATFORM_DRAGNCARDS,
    ) -> BranchSession:
        """Create a fresh real game-service session for a branchable restore.

        A ``mode="new"`` restore must own a real DragnCards room so it can import
        the base state (or replay from the start) without touching the original
        timeline. We create one via game-service ``POST /games`` using the
        resolved ``plugin_name`` slug, and return the new session together with
        its room slug (the branch ``game_id`` and the room to open).

        When ``ephemeral`` is true the session is created as a non-emitting,
        server-reaped reconstruction (for viewing only).
        """
        try:
            return await self._game_service.create_session(
                plugin_name, ephemeral=ephemeral, platform=platform
            )
        except TypeError:
            if platform != PLATFORM_DRAGNCARDS:
                raise
            return await self._game_service.create_session(
                plugin_name, ephemeral=ephemeral
            )

    async def _restore_agent_context(
        self,
        game_id: str,
        game_session_id: str,
        target_seq: int,
        mode: RestoreMode,
        platform: Platform = PLATFORM_DRAGNCARDS,
    ) -> tuple[str | None, str | None]:
        """Rebuild the agent's conversation context; report, never raise, a miss.

        Returns the orchestrator session id (or None) and a human-readable note
        explaining a None.

        This layer is secondary to the game-state restore, and it must not be
        able to fail one. An in-place rewind asks the orchestrator to *resume* the
        agent session bound to this game, and the orchestrator answers ``404``
        when no ACTIVE session is bound to it — which is the normal state for any
        game being browsed in history, because the session that played it has
        since been terminated. Treating that as fatal reported a completed rewind
        as a failed one, and reported it as a bare "404" that named neither the
        service nor the cause. The game state has already been overwritten by the
        time this runs and an in-place rewind has nothing to roll back to, so
        raising here also left the live game rewound while telling the user the
        restore had failed.
        """
        agent_event = await self._repository.get_latest_agent_event_at_or_before(
            game_id, target_seq, platform
        )
        if agent_event is None:
            logger.info(
                "No agent event at/<= seq=%s for game=%s; skipping context restore",
                target_seq,
                game_id,
            )
            return None, (
                "No agent decision was recorded at or before this moment, so "
                "there was no agent conversation to rebuild."
            )
        conversation_context = _extract_conversation_context(agent_event)
        if not conversation_context:
            # The orchestrator accepts an empty conversation and reports success,
            # so passing one through would claim the agent context was rebuilt
            # when nothing was. A recording can honestly carry none: a history
            # imported from a `minimal` bundle has the prompt material omitted by
            # design, and the header says so. Report that rather than restoring a
            # conversation the model never had.
            logger.info(
                "Agent event seq=%s for game=%s carries no captured "
                "conversation; skipping context restore",
                agent_event.seq,
                game_id,
            )
            return None, (
                "The agent decision recorded at this moment carries no captured "
                "conversation, so there was nothing to rebuild. A history "
                "imported from a 'minimal' bundle has its prompt material "
                "omitted by design."
            )
        try:
            response = await self._orchestrator.restore_session(
                game_id=game_session_id,
                conversation_context=conversation_context,
                mode=mode,
            )
        except httpx.HTTPStatusError as exc:
            # Gated on the mode deliberately. Only the orchestrator's "in place"
            # branch looks a session up and can legitimately answer 404; its "new"
            # branch unconditionally creates one and has no 404 path at all, so a
            # 404 there means the endpoint itself was not reached — a wrong
            # AGENT_ORCHESTRATOR_BASE_URL, or a version skew that moved the route.
            # This is the ONLY call history-service makes to agent-orchestrator, so
            # a misconfigured URL has exactly one observable symptom; swallowing it
            # would turn a broken deployment into a reassuring note and leave no
            # other signal to catch it.
            if mode == "in_place" and exc.response.status_code == 404:
                logger.info(
                    "No active agent session bound to game=%s; game state was "
                    "restored without the agent conversation",
                    game_session_id,
                )
                return None, (
                    "The game state was restored, but no active agent session is "
                    "bound to this game, so the agent conversation was not "
                    "rebuilt. Start an agent on the restored game to continue "
                    "play."
                )
            raise
        return response.get("session_id"), None

    async def _verify_status(
        self,
        game_session_id: str,
        replay_events: list[StoredEvent],
        target_seq: int,
    ) -> tuple[bool | None, str | None]:
        expected_status = _expected_status(replay_events, target_seq)
        if expected_status is None:
            return None, None
        try:
            state = await self._game_service.get_state(game_session_id)
        except Exception:  # noqa: BLE001
            return None, None
        actual_status = _status_from_state(state)
        if actual_status is None:
            return None, None
        if actual_status == expected_status:
            return True, None
        divergence = (
            f"post-restore status {actual_status!r} differs from recorded "
            f"{expected_status!r} at seq {target_seq}"
        )
        logger.warning(divergence)
        return False, divergence


def _choose_base(
    snapshot: StoredSnapshot | None,
    state_event: StoredEvent | None,
    plugin_name: str | None,
) -> _RestoreBase | None:
    """Pick the densest full-state base at/<= the target, or None if there is none.

    A game-state event wins a tie with a snapshot at the same seq: both describe
    the same moment, and the event's document is synthesized here rather than
    read from a second table.
    """
    if state_event is not None and (
        snapshot is None or state_event.seq >= snapshot.snapshot_at_seq
    ):
        game = _game_from_state_event(state_event)
        # ``plugin_name`` is required to synthesize the load document; without it
        # the state event is unusable and the snapshot (if any) is the only base.
        if game is not None and plugin_name:
            return _RestoreBase(
                document={
                    "schema_version": 1,
                    "plugin_name": plugin_name,
                    "game": game,
                },
                seq=state_event.seq,
            )
    if snapshot is not None:
        return _RestoreBase(document=snapshot.snapshot, seq=snapshot.snapshot_at_seq)
    return None


def _game_from_state_event(event: StoredEvent | None) -> dict[str, Any] | None:
    """Extract the inner DragnCards ``game`` payload from a state event.

    A game-state event payload carries ``state`` (the full session state); its
    ``game`` field is the inner document accepted by game-service ``set_game``.
    """
    if event is None:
        return None
    state = event.payload.get("state")
    if isinstance(state, dict):
        game = state.get("game")
        if isinstance(game, dict):
            return game
    return None


def _plugin_name_from_snapshot(snapshot: StoredSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    plugin_name = snapshot.snapshot.get("plugin_name")
    if isinstance(plugin_name, str) and plugin_name:
        return plugin_name
    return None


def _is_mutating_event(event: StoredEvent) -> bool:
    """A game-service event is replayable when it carries an action descriptor."""
    return bool(event.payload.get("action_path"))


def _extract_conversation_context(event: StoredEvent) -> list[dict[str, Any]]:
    """Return the captured messages as a flat list.

    The orchestrator restore endpoint expects ``conversation_context`` to be a
    list of message dicts. Stored events carry it either as that list directly
    or wrapped under a ``messages`` key; normalize both to the list form.
    """
    context = event.payload.get("conversation_context")
    if isinstance(context, list):
        return [m for m in context if isinstance(m, dict)]
    if isinstance(context, dict):
        messages = context.get("messages")
        if isinstance(messages, list):
            return [m for m in messages if isinstance(m, dict)]
    return []


def _expected_status(events: list[StoredEvent], target_seq: int) -> str | None:
    """The last recorded status at or before the target, from the replay range.

    The range is already filtered to ``game-service`` in SQL, so this only has to
    bound by ``seq``. A pure function over a caller-supplied list, so it does not
    assume that filter — an unfiltered list still yields the same answer, because
    only ``game-service`` payloads carry ``status``/``mode``.
    """
    for event in reversed(events):
        if event.seq > target_seq:
            continue
        status = event.payload.get("status") or event.payload.get("mode")
        if status:
            return str(status)
    return None


def _status_from_state(state: dict[str, Any]) -> str | None:
    inner = state.get("state") if isinstance(state.get("state"), dict) else state
    if isinstance(inner, dict):
        status = inner.get("mode") or inner.get("status")
        if status:
            return str(status)
    return None
