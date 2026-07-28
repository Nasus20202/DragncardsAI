from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from history_service.integrations.game_service import GameServiceClient
from history_service.integrations.orchestrator import OrchestratorClient
from history_service.schemas.envelope import StoredEvent, StoredSnapshot
from history_service.storage.repository import Repository
from history_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

RestoreMode = Literal["new", "in_place"]


class RestoreError(Exception):
    """Raised for client-correctable restore failures (e.g. out-of-range seq)."""


@dataclass
class RestoreResult:
    game_id: str
    target_seq: int
    mode: RestoreMode
    game_session_id: str
    orchestrator_session_id: str | None
    snapshot_at_seq: int | None
    replayed_event_seqs: list[int] = field(default_factory=list)
    status_verified: bool | None = None
    divergence: str | None = None


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
    ) -> RestoreResult:
        """Traced entry point; the workflow itself is :meth:`_restore`.

        Restore is a multi-step, repo-specific workflow (snapshot load, forward
        replay, agent-context restore, verify) that generic library
        instrumentation cannot explain, so it gets one span covering the whole
        thing. Only identifiers and mode flags are attached — never the replayed
        events or the restored state.
        """
        with tracer.start_as_current_span(
            "history.restore",
            attributes={
                "game.id": game_id,
                "history.target_seq": target_seq,
                "history.restore_mode": mode,
                "history.ephemeral": ephemeral,
            },
        ):
            return await self._restore(
                game_id,
                target_seq=target_seq,
                mode=mode,
                ephemeral=ephemeral,
            )

    async def _restore(
        self,
        game_id: str,
        *,
        target_seq: int,
        mode: RestoreMode,
        ephemeral: bool,
    ) -> RestoreResult:
        # 1. Validate target_seq is in range BEFORE mutating anything.
        latest_seq = await self._repository.get_latest_seq(game_id)
        if latest_seq is None or target_seq < 1 or target_seq > latest_seq:
            raise RestoreError(
                f"target_seq {target_seq} is out of range for game {game_id!r} "
                f"(valid range: 1..{latest_seq if latest_seq else 0})"
            )

        # 2. Resolve the nearest snapshot at/<= target up front: it is both the
        #    game-state base and the source of the ``plugin_name`` needed to
        #    materialize a fresh branch session.
        snapshot = await self._repository.get_latest_snapshot_at_or_before(
            game_id, target_seq
        )

        # 3. Determine the target game-service session.
        #    - "in_place": rewind the existing live session (same game_id).
        #    - "new": create a fresh real DragnCards session, leaving the
        #      original timeline intact, then load + replay into it.
        #
        # ``created_new_session`` tracks whether we materialized a real
        # game-service room for this restore so we can roll it back if a later
        # step fails (a half-built branch must not be left behind).
        created_new_session = False
        if mode == "in_place":
            # An in-place rewind MUST start from a clean base before forward
            # replay, otherwise replaying (low_exclusive, target] on top of the
            # un-rewound live state double-applies every event. The only clean
            # base we can establish in place is loading a snapshot at/<= target.
            # Without such a snapshot there is no safe way to rewind in place, so
            # reject rather than corrupt the live session.
            if snapshot is None:
                raise RestoreError(
                    f"cannot rewind game {game_id!r} in place to seq {target_seq}: "
                    "no snapshot at or before the target exists to establish a "
                    "clean base (use mode='new', or take a snapshot first)"
                )
            game_session_id = game_id
        else:
            # Resolve the plugin slug needed to materialize the branch room.
            # Prefer the nearest snapshot, then any snapshot, then the earliest
            # game-state event (which also records plugin_name) — the last
            # fallback lets short games with no snapshot still be reconstructed.
            plugin_name = await self._resolve_plugin_name(game_id, snapshot)
            # An ephemeral branch is a non-emitting, server-reaped reconstruction
            # for viewing only; pass the flag through so the game-service tags the
            # session and never emits history for it.
            game_session_id = await self._create_branch_session(
                plugin_name, ephemeral=ephemeral
            )
            created_new_session = True

        # 4. Apply the restore: load the base snapshot, replay forward, restore
        #    agent context, then verify. Any failure mid-apply leaves a partial
        #    state; surface it as a RestoreError (the router maps it to a clean
        #    4xx instead of an unhandled 500) and, for a freshly created branch,
        #    best-effort delete the room we created so it is not orphaned.
        try:
            return await self._apply_restore(
                game_id=game_id,
                game_session_id=game_session_id,
                target_seq=target_seq,
                mode=mode,
                snapshot=snapshot,
                ephemeral=ephemeral,
                plugin_name=plugin_name if mode != "in_place" else None,
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
        snapshot: StoredSnapshot | None,
        ephemeral: bool = False,
        plugin_name: str | None = None,
    ) -> RestoreResult:
        # Game-state layer: load the densest available base at/<= target, then
        # forward-replay any mutating actions after it.
        #
        # Two base sources carry full game state: a periodic snapshot, and any
        # game-state EVENT (its payload embeds the complete state). Snapshots are
        # sparse (every N events), while game-state events are dense (one per
        # game action), so the nearest game-state event is usually at or just
        # below the target and needs little-to-no replay. Crucially, replay only
        # covers actions recorded as replayable generic actions — setup actions
        # like deck loading are NOT, so replaying from seq 0 yields an empty
        # board. Loading a full-state base avoids that entirely. We pick whichever
        # base is more recent. ``plugin_name`` is required to synthesize a load
        # document from a state event; it is only passed for branch ("new")
        # restores (in_place keeps the prior snapshot-required semantics).
        state_event = None
        if plugin_name:
            state_event = await self._repository.get_latest_state_event_at_or_before(
                game_id, target_seq
            )
        snapshot_seq = snapshot.snapshot_at_seq if snapshot is not None else None
        state_event_seq = state_event.seq if state_event is not None else None

        if state_event_seq is not None and (
            snapshot_seq is None or state_event_seq >= snapshot_seq
        ):
            # Load the full state embedded in the nearest game-state event.
            game = _game_from_state_event(state_event)
            if game is not None:
                await self._game_service.load_snapshot(
                    game_session_id,
                    {"schema_version": 1, "plugin_name": plugin_name, "game": game},
                )
                low_exclusive = state_event_seq
                snapshot_at_seq: int | None = state_event_seq
            else:
                low_exclusive = snapshot_seq or 0
                snapshot_at_seq = snapshot_seq
                if snapshot is not None:
                    await self._game_service.load_snapshot(
                        game_session_id, snapshot.snapshot
                    )
        elif snapshot is not None:
            await self._game_service.load_snapshot(game_session_id, snapshot.snapshot)
            low_exclusive = snapshot_seq or 0
            snapshot_at_seq = snapshot_seq
        else:
            # No full-state base available: replay from the start of the log.
            # (in_place restore without a snapshot is rejected before reaching
            # here, so this path only applies to mode="new".)
            low_exclusive = 0
            snapshot_at_seq = None

        replay_events = await self._repository.get_events_in_range(
            game_id, low_exclusive=low_exclusive, high_inclusive=target_seq
        )
        replayed_seqs: list[int] = []
        for event in replay_events:
            # Agent decision events are NEVER replayed as game mutations.
            if event.actor != "game-service":
                continue
            if not _is_mutating_event(event):
                continue
            await self._game_service.replay_action(game_session_id, event.payload)
            replayed_seqs.append(event.seq)

        # Agent-context layer: latest agent event at/<= target -> orchestrator.
        # An ephemeral reconstruction is a view-only board, so it does not need
        # (and must not create) an orchestrator agent session: skip this layer.
        if ephemeral:
            orchestrator_session_id = None
        else:
            orchestrator_session_id = await self._restore_agent_context(
                game_id, game_session_id, target_seq, mode
            )

        # Verify post-restore status against the stored event, if available.
        status_verified, divergence = await self._verify_status(
            game_session_id, replay_events, target_seq
        )

        return RestoreResult(
            game_id=game_id,
            target_seq=target_seq,
            mode=mode,
            game_session_id=game_session_id,
            orchestrator_session_id=orchestrator_session_id,
            snapshot_at_seq=snapshot_at_seq,
            replayed_event_seqs=replayed_seqs,
            status_verified=status_verified,
            divergence=divergence,
        )

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

    async def _resolve_plugin_name(
        self, game_id: str, snapshot: StoredSnapshot | None
    ) -> str:
        """Resolve the plugin slug used to materialize a branch session.

        The slug is recorded both in snapshot documents and on every game-state
        event payload. Prefer the nearest snapshot, then any snapshot, then the
        earliest game-state event — so a branchable restore works even when no
        snapshot has been taken yet (short games).
        """
        plugin_name = _plugin_name_from_snapshot(snapshot)
        if not plugin_name:
            all_snapshots = await self._repository.list_snapshots(game_id)
            plugin_name = _plugin_name_from_snapshot(
                all_snapshots[0] if all_snapshots else None
            )
        if not plugin_name:
            earliest = await self._repository.get_earliest_state_event(game_id)
            if earliest is not None:
                candidate = earliest.payload.get("plugin_name")
                if isinstance(candidate, str) and candidate:
                    plugin_name = candidate
        if not plugin_name:
            raise RestoreError(
                "cannot create a new branch session: no plugin_name is recorded "
                "for this game (no snapshot and no game-state event carries one)"
            )
        return plugin_name

    async def _create_branch_session(
        self, plugin_name: str, *, ephemeral: bool = False
    ) -> str:
        """Create a fresh real game-service session for a branchable restore.

        A ``mode="new"`` restore must own a real DragnCards room so it can import
        the snapshot (or replay from the start) without touching the original
        timeline. We create one via game-service ``POST /games`` using the
        resolved ``plugin_name`` slug, and return the new session id (the branch
        ``game_id``).

        When ``ephemeral`` is true the session is created as a non-emitting,
        server-reaped reconstruction (for viewing only).
        """
        return await self._game_service.create_session(plugin_name, ephemeral=ephemeral)

    async def _restore_agent_context(
        self,
        game_id: str,
        game_session_id: str,
        target_seq: int,
        mode: RestoreMode,
    ) -> str | None:
        agent_event = await self._repository.get_latest_agent_event_at_or_before(
            game_id, target_seq
        )
        if agent_event is None:
            logger.info(
                "No agent event at/<= seq=%s for game=%s; skipping context restore",
                target_seq,
                game_id,
            )
            return None
        conversation_context = _extract_conversation_context(agent_event)
        response = await self._orchestrator.restore_session(
            game_id=game_session_id,
            conversation_context=conversation_context,
            mode=mode,
        )
        return response.get("session_id")

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
    for event in reversed(events):
        if event.actor != "game-service" or event.seq > target_seq:
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
