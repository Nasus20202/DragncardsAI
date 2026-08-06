from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from eval_service.error_detail import sanitize_error_detail
from eval_service.storage.models import (
    NON_TERMINAL_STATUSES,
    EvaluatedTargetRow,
    EvaluationRequestRow,
    utc_now,
)

# The single advisory-lock key every claimer contends on. It must be ONE
# constant: two claimers taking different keys serialize against nobody, which
# is exactly the overshoot the lock exists to prevent. The value is the ASCII
# bytes of "EVAL" -- arbitrary, but fixed and greppable.
CLAIM_ADVISORY_LOCK_KEY = 0x4556414C


@dataclass(frozen=True)
class ClaimResult:
    """Outcome of an at-most-once target claim.

    ``claimed`` is True when this caller won the durable claim (the target was
    inserted or re-claimed under ``force``) and SHOULD perform the evaluation.
    ``existing_status`` carries the prior status when the claim was a no-op.
    """

    claimed: bool
    target_id: int | None
    existing_status: str | None = None


@dataclass(frozen=True)
class ReclaimResult:
    """What one stale-claim sweep did, so the worker can log it.

    ``reclaimed_ids`` went back to ``pending`` and will be claimed again;
    ``failed_ids`` had burned through ``max_attempts`` and were given up on. Both
    are returned rather than a bare count because the two mean very different
    things operationally -- a steady trickle of reclaims is a crashing worker, a
    failure is a target nobody should keep paying to grade.
    """

    reclaimed_ids: tuple[int, ...]
    failed_ids: tuple[int, ...]


def _within_capacity(
    candidates: list[tuple[int, str]],
    *,
    capacity: int,
    per_game_limit: int | None,
    running_by_game: dict[str, int],
) -> list[int]:
    """The candidate ids that fit the remaining global and per-game capacity.

    Candidates arrive in drain order; this walks them once and takes each one only
    while its game still has room, stopping at the global capacity. Per-game
    counting STARTS from the rows already ``running`` for that game, so the cap
    covers work in flight and not merely work claimed in this batch.
    """
    if capacity <= 0:
        return []
    taken: list[int] = []
    per_game = dict(running_by_game)
    for target_id, game_id in candidates:
        if per_game_limit is not None:
            if per_game.get(game_id, 0) >= per_game_limit:
                continue
            per_game[game_id] = per_game.get(game_id, 0) + 1
        taken.append(target_id)
        if len(taken) >= capacity:
            break
    return taken


class Repository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    # -- requests -----------------------------------------------------------

    async def create_request(
        self,
        *,
        request_id: str,
        game_id: str,
        scope: str,
        selection: dict[str, Any],
        force: bool,
        judge_config: dict[str, Any] | None = None,
    ) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                session.add(
                    EvaluationRequestRow(
                        request_id=request_id,
                        game_id=game_id,
                        scope=scope,
                        selection_json=selection,
                        force=1 if force else 0,
                        judge_config_json=judge_config,
                        created_at=utc_now(),
                    )
                )

    async def get_request(self, request_id: str) -> EvaluationRequestRow | None:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EvaluationRequestRow).where(
                    EvaluationRequestRow.request_id == request_id
                )
            )
            return result.scalar_one_or_none()

    async def delete_request(self, request_id: str) -> bool:
        """Delete a request and all its target rows in one transaction.

        Returns whether the request existed. This removes the eval-service's own
        queue tracking only; verdicts already recorded as history-service events
        are independent and untouched. Callers MUST verify the request is fully
        terminal first: deleting a request with a non-terminal target would drop
        a row a worker may still be draining.
        """
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    EvaluatedTargetRow.__table__.delete().where(
                        EvaluatedTargetRow.request_id == request_id
                    )
                )
                result = await session.execute(
                    EvaluationRequestRow.__table__.delete().where(
                        EvaluationRequestRow.request_id == request_id
                    )
                )
                return (result.rowcount or 0) > 0

    async def delete_terminal_requests(self) -> int:
        """Delete every request that has NO non-terminal target (clear-all).

        Mirrors the active-filter subquery used by ``list_requests``, negated:
        a request is deletable when its ``request_id`` is NOT among the requests
        with a pending/running target. Requests with at least one non-terminal
        target are left intact. Returns the number of requests deleted.
        """
        async with self._session_factory() as session:
            async with session.begin():
                active_request_ids = select(EvaluatedTargetRow.request_id).where(
                    EvaluatedTargetRow.status.in_(tuple(NON_TERMINAL_STATUSES))
                )
                # Delete the targets of terminal requests first (FK child), then
                # the requests themselves, both scoped by the same negated
                # active subquery so only fully-terminal requests are removed.
                await session.execute(
                    EvaluatedTargetRow.__table__.delete().where(
                        EvaluatedTargetRow.request_id.not_in(active_request_ids)
                    )
                )
                result = await session.execute(
                    EvaluationRequestRow.__table__.delete().where(
                        EvaluationRequestRow.request_id.not_in(active_request_ids)
                    )
                )
                return result.rowcount or 0

    # -- target claims ------------------------------------------------------

    async def claim_target(
        self,
        *,
        request_id: str,
        game_id: str,
        target_seq: int,
        scope: str,
        round_span: tuple[int, int] | None,
        force: bool,
        judge_config: dict[str, Any] | None = None,
        player: str = "",
    ) -> ClaimResult:
        """Durably claim a target for evaluation, at most once.

        Inserts a ``pending`` row with ``ON CONFLICT DO NOTHING`` on the unique
        ``(game_id, target_seq, scope, player)`` key. If a row already exists:
          * without ``force`` the claim is a no-op (the existing verdict stands);
          * with ``force`` the existing row is reset to ``pending`` (re-linked to
            this request) so a fresh verdict is produced.
        """
        now = utc_now()
        round_from = round_span[0] if round_span else None
        round_to = round_span[1] if round_span else None
        # The insert/conflict-check AND any force-reset all happen in ONE
        # transaction so a force re-claim is atomic with respect to a worker
        # that may be mid-evaluation on the same row.
        async with self._session_factory() as session:
            async with session.begin():
                dialect = session.bind.dialect.name
                insert_stmt = (
                    pg_insert(EvaluatedTargetRow)
                    if dialect == "postgresql"
                    else sqlite_insert(EvaluatedTargetRow)
                )
                insert_stmt = insert_stmt.values(
                    request_id=request_id,
                    game_id=game_id,
                    target_seq=target_seq,
                    scope=scope,
                    player=player,
                    round_from_seq=round_from,
                    round_to_seq=round_to,
                    status="pending",
                    judge_config_json=judge_config,
                    created_at=now,
                    updated_at=now,
                ).on_conflict_do_nothing(
                    index_elements=["game_id", "target_seq", "scope", "player"]
                )
                result = await session.execute(insert_stmt)
                inserted = (result.rowcount or 0) > 0
                # Resolve the row id inside the same transaction.
                row = await self._get_target(
                    session, game_id, target_seq, scope, player
                )

                if inserted:
                    return ClaimResult(claimed=True, target_id=row.id if row else None)
                # A row already existed.
                if row is None:
                    # Lost a race then the row vanished; treat as unclaimed.
                    return ClaimResult(claimed=False, target_id=None)
                if not force:
                    return ClaimResult(
                        claimed=False,
                        target_id=row.id,
                        existing_status=row.status,
                    )
                # Force: reset the existing row to pending and re-link to this
                # request, in the SAME transaction as the conflict check.
                #
                # ``attempts`` moves too, because a force reset REVOKES whatever
                # claim was live on this row. Without the bump, a worker still
                # mid-evaluation under the old claim would find the row
                # ``running`` again once the forced re-claim started and write
                # its stale verdict over the fresh one -- the exact race the
                # epoch exists to close.
                await session.execute(
                    update(EvaluatedTargetRow)
                    .where(EvaluatedTargetRow.id == row.id)
                    .values(
                        request_id=request_id,
                        status="pending",
                        attempts=EvaluatedTargetRow.attempts + 1,
                        error=None,
                        verdict_json=None,
                        judge_config_json=judge_config,
                        round_from_seq=round_from,
                        round_to_seq=round_to,
                        updated_at=utc_now(),
                    )
                )
                return ClaimResult(claimed=True, target_id=row.id)

    async def _get_target(
        self,
        session: AsyncSession,
        game_id: str,
        target_seq: int,
        scope: str,
        player: str = "",
    ) -> EvaluatedTargetRow | None:
        result = await session.execute(
            select(EvaluatedTargetRow).where(
                EvaluatedTargetRow.game_id == game_id,
                EvaluatedTargetRow.target_seq == target_seq,
                EvaluatedTargetRow.scope == scope,
                EvaluatedTargetRow.player == player,
            )
        )
        return result.scalar_one_or_none()

    # -- target lifecycle ---------------------------------------------------

    async def finalize_completed(
        self,
        target_id: int,
        verdict: dict[str, Any],
        *,
        attempts: int | None = None,
    ) -> None:
        await self._transition_running(
            target_id,
            attempts=attempts,
            status="completed",
            verdict_json=verdict,
            error=None,
        )

    async def mark_skipped(
        self, target_id: int, error: str, *, attempts: int | None = None
    ) -> None:
        """Record a DELIBERATE skip (a non-strategic action) with its reason.

        Reserved for "there was no decision to grade here". A failure uses
        ``mark_failed`` so a client can tell an error apart from a designed skip.
        """
        await self._transition_running(
            target_id,
            attempts=attempts,
            status="skipped",
            error=sanitize_error_detail(error),
        )

    async def mark_failed(
        self, target_id: int, error: str, *, attempts: int | None = None
    ) -> None:
        await self._transition_running(
            target_id,
            attempts=attempts,
            status="failed",
            error=sanitize_error_detail(error),
        )

    async def record_attempt_error(
        self, target_id: int, error: str, *, attempts: int | None = None
    ) -> bool:
        """Record a mid-evaluation failure on a target that is still ``running``.

        A judge attempt that failed and will be retried is detail the user must be
        able to read WHILE the evaluation continues, so it is written to Postgres
        rather than held in the worker — any poller or stream then reads it from
        the authoritative snapshot. The status is left untouched (the target is
        still being worked on), and the ``status='running'`` + epoch guard means a
        concurrent cancel, reclaim or force re-claim is never clobbered. Returns
        whether a row was actually updated.
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(EvaluatedTargetRow)
                    .where(*self._running_under_claim(target_id, attempts))
                    .values(error=sanitize_error_detail(error), updated_at=utc_now())
                )
                return (result.rowcount or 0) > 0

    @staticmethod
    def _running_under_claim(target_id: int, attempts: int | None) -> tuple[Any, ...]:
        """The WHERE terms for "this row is still running UNDER MY claim".

        ``status='running'`` alone is not that question: a reclaim or a force
        reset hands the row to a NEW claim which puts it back to ``running``, and
        a stale worker's write would then pass the status guard and overwrite the
        new claim's outcome. Adding ``attempts = :claimed`` fences that write out
        — the epoch moved when the claim was revoked, so the UPDATE matches no
        rows and is correctly discarded.

        ``attempts=None`` means "no epoch known" and keeps the historical
        status-only guard. It is not a loophole to be closed: some writes
        legitimately have no claimed epoch (a target failed before it was ever
        claimed), and inventing one would fence a write that should land.
        """
        conditions: list[Any] = [
            EvaluatedTargetRow.id == target_id,
            EvaluatedTargetRow.status == "running",
        ]
        if attempts is not None:
            conditions.append(EvaluatedTargetRow.attempts == attempts)
        return tuple(conditions)

    async def _transition_running(
        self, target_id: int, *, attempts: int | None = None, **values: Any
    ) -> None:
        """Move a target out of ``running`` to a terminal state, conditionally.

        Guarded by :meth:`_running_under_claim`, so a concurrent force re-claim or
        stale-claim reclaim (both of which hand the row to a NEW claim) is never
        clobbered by the prior worker finalizing its abandoned evaluation: the
        UPDATE simply matches no rows and is a no-op.
        """
        async with self._session_factory() as session:
            async with session.begin():
                values["updated_at"] = utc_now()
                await session.execute(
                    update(EvaluatedTargetRow)
                    .where(*self._running_under_claim(target_id, attempts))
                    .values(**values)
                )

    async def defer_to_pending(
        self, target_id: int, *, attempts: int | None = None
    ) -> bool:
        """Reset a ``running`` target back to ``pending`` so a later drain retries.

        Used to gate a higher-level (round/game) target while the lower-level
        children it depends on are still being graded: the roll-up is re-queued
        rather than produced against incomplete child context. The
        ``status='running'`` + epoch guard means a concurrent cancel, reclaim or
        force re-claim is never clobbered. Returns whether a row was actually
        re-deferred.
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(EvaluatedTargetRow)
                    .where(*self._running_under_claim(target_id, attempts))
                    .values(status="pending", updated_at=utc_now())
                )
                return (result.rowcount or 0) > 0

    async def count_nonterminal_children(
        self, *, game_id: str, from_seq: int, to_seq: int, child_scope: str
    ) -> int:
        """Count still-in-flight (pending/running) child targets in a span.

        A round/game roll-up depends on the targets at ``child_scope`` whose
        ``target_seq`` falls within ``[from_seq, to_seq]``; while any such child
        is non-terminal the roll-up must wait. State is read from Postgres so the
        gate holds no in-memory dependency graph.
        """
        async with self._session_factory() as session:
            return (
                await session.scalar(
                    select(func.count())
                    .select_from(EvaluatedTargetRow)
                    .where(
                        EvaluatedTargetRow.game_id == game_id,
                        EvaluatedTargetRow.scope == child_scope,
                        EvaluatedTargetRow.target_seq >= from_seq,
                        EvaluatedTargetRow.target_seq <= to_seq,
                        EvaluatedTargetRow.status.in_(tuple(NON_TERMINAL_STATUSES)),
                    )
                )
            ) or 0

    async def get_target_by_id(self, target_id: int) -> EvaluatedTargetRow | None:
        async with self._session_factory() as session:
            return await session.get(EvaluatedTargetRow, target_id)

    async def get_target_status(self, target_id: int) -> str | None:
        """Return the current durable status of a target (``None`` if missing).

        Used to re-check ``running`` immediately before a verdict write-back so a
        cancel (or force re-claim) that landed after the target was claimed but
        before the in-flight task could be aborted never leaves a stale verdict.
        """
        async with self._session_factory() as session:
            return await session.scalar(
                select(EvaluatedTargetRow.status).where(
                    EvaluatedTargetRow.id == target_id
                )
            )

    async def get_target_claim(self, target_id: int) -> tuple[str | None, int | None]:
        """Return a target's ``(status, attempts)`` — its status and claim epoch.

        The status alone cannot answer the question a worker actually needs to
        ask before writing back: not *"is this row running?"* but *"is this row
        still running UNDER MY CLAIM?"*. A row that was reset and re-claimed by
        another worker is ``running`` again, so a status-only check passes and
        the superseded worker goes on to emit a verdict event nobody asked for.
        Returning the epoch too lets the caller compare it against the one it
        claimed at, and abort before writing anything to history.
        """
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(
                        EvaluatedTargetRow.status, EvaluatedTargetRow.attempts
                    ).where(EvaluatedTargetRow.id == target_id)
                )
            ).first()
            if row is None:
                return None, None
            return row[0], row[1]

    async def list_targets_for_request(
        self, request_id: str
    ) -> list[EvaluatedTargetRow]:
        async with self._session_factory() as session:
            result = await session.execute(
                select(EvaluatedTargetRow)
                .where(EvaluatedTargetRow.request_id == request_id)
                .order_by(EvaluatedTargetRow.target_seq.asc())
            )
            return list(result.scalars().all())

    async def list_requests(
        self, *, limit: int, active_only: bool
    ) -> list[tuple[EvaluationRequestRow, list[EvaluatedTargetRow]]]:
        """List recent evaluation requests across all games, newest-first.

        Returns each request paired with its targets (ordered by ``target_seq``)
        so a caller can build a per-request summary. When ``active_only`` is set,
        only requests with at least one non-terminal (pending/running) target are
        returned; the filter is applied in SQL so paging by ``limit`` selects from
        the already-filtered set. The result is bounded by ``limit``. All state is
        derived from Postgres; there is no in-memory queue.
        """
        async with self._session_factory() as session:
            stmt = select(EvaluationRequestRow)
            if active_only:
                active_request_ids = select(EvaluatedTargetRow.request_id).where(
                    EvaluatedTargetRow.status.in_(tuple(NON_TERMINAL_STATUSES))
                )
                stmt = stmt.where(
                    EvaluationRequestRow.request_id.in_(active_request_ids)
                )
            stmt = stmt.order_by(EvaluationRequestRow.created_at.desc()).limit(limit)
            requests = list((await session.execute(stmt)).scalars().all())
            if not requests:
                return []
            request_ids = [r.request_id for r in requests]
            target_rows = list(
                (
                    await session.execute(
                        select(EvaluatedTargetRow)
                        .where(EvaluatedTargetRow.request_id.in_(request_ids))
                        .order_by(EvaluatedTargetRow.target_seq.asc())
                    )
                )
                .scalars()
                .all()
            )
            by_request: dict[str, list[EvaluatedTargetRow]] = {
                rid: [] for rid in request_ids
            }
            for row in target_rows:
                by_request[row.request_id].append(row)
            return [(r, by_request[r.request_id]) for r in requests]

    async def claim_pending_targets(
        self,
        *,
        limit: int = 64,
        global_limit: int | None = None,
        per_game_limit: int | None = None,
    ) -> list[EvaluatedTargetRow]:
        """Atomically claim pending targets and transition them to ``running``.

        Returns ONLY the targets this caller successfully claimed, so two
        replicas draining concurrently never both pick the same row (the
        design's at-most-once-per-replica guarantee). Pending state lives
        durably in Postgres (no in-memory queue), so a restart resumes work.

        ``global_limit`` / ``per_game_limit`` are the CONCURRENCY CAPS, applied
        here rather than by an in-process semaphore: the rows already recorded
        ``running`` are counted in this same transaction and only the remaining
        capacity is claimed. That keeps the caps out of process memory entirely
        (this repo forbids in-memory state), makes them survive a restart, and
        stops a second replica from bypassing them with its own semaphores.
        ``None`` for either means no cap from that side.

        On PostgreSQL the candidate rows are locked with ``FOR UPDATE SKIP
        LOCKED`` so concurrent drainers select disjoint sets; on SQLite (tests)
        the same transaction serializes claims, so the lock clause is omitted
        and the conditional ``status='pending'`` UPDATE is the at-most-once
        guard.

        The whole transaction is additionally serialized against other claimers
        by a transaction-scoped advisory lock on PostgreSQL — see below for why
        ``SKIP LOCKED`` alone leaves the cap unenforced.
        """
        async with self._session_factory() as session:
            async with session.begin():
                dialect = session.bind.dialect.name
                if dialect == "postgresql":
                    # SERIALIZE THE WHOLE CLAIM. ``FOR UPDATE SKIP LOCKED`` locks
                    # the pending CANDIDATES; it does not lock the ``running``
                    # rows the capacity COUNT below reads. Under READ COMMITTED
                    # two replicas claiming at once each see the pre-claim count
                    # and each spend the same capacity, so the global cap
                    # overshoots by up to the replica count. That is not a
                    # double-grading bug (the claimed sets stay disjoint) but a
                    # SPEND-control one: a provider guard that doubles when
                    # someone scales to two replicas is not a guard.
                    #
                    # ``xact`` scope is what makes this safe to hold: it is
                    # released at commit, at rollback, AND when the backend dies,
                    # so unlike the claim lease it can never leave stuck state.
                    # The critical section is a COUNT, a bounded SELECT and one
                    # UPDATE — single-digit milliseconds against work items that
                    # take seconds — and the evaluations themselves run entirely
                    # outside it.
                    #
                    # SQLite (tests) already serializes writers, so the lock is
                    # skipped there, exactly as ``FOR UPDATE SKIP LOCKED`` is.
                    await session.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": CLAIM_ADVISORY_LOCK_KEY},
                    )
                capacity = limit
                if global_limit is not None:
                    running_total = (
                        await session.scalar(
                            select(func.count())
                            .select_from(EvaluatedTargetRow)
                            .where(EvaluatedTargetRow.status == "running")
                        )
                    ) or 0
                    capacity = min(capacity, max(0, global_limit - running_total))
                    if capacity == 0:
                        return []
                running_by_game: dict[str, int] = {}
                if per_game_limit is not None:
                    rows = await session.execute(
                        select(EvaluatedTargetRow.game_id, func.count())
                        .where(EvaluatedTargetRow.status == "running")
                        .group_by(EvaluatedTargetRow.game_id)
                    )
                    running_by_game = dict(rows.all())  # type: ignore[arg-type]

                # Games already AT their per-game cap are excluded here, before
                # the LIMIT window is taken, rather than being fetched and
                # dropped by ``_within_capacity`` afterwards. One whole-game
                # request can leave far more than ``limit`` rows pending for a
                # single game (``EVAL_MAX_TARGETS_PER_REQUEST`` is 200), so once
                # that game saturates, a window taken over all pending rows
                # contains nothing BUT its rows: every candidate is discarded,
                # the claim returns empty, and a second game's targets are never
                # even considered while global capacity sits idle.
                saturated_games = (
                    [
                        game_id
                        for game_id, running in running_by_game.items()
                        if running >= per_game_limit
                    ]
                    if per_game_limit is not None
                    else []
                )
                stmt = (
                    select(EvaluatedTargetRow.id, EvaluatedTargetRow.game_id)
                    .where(EvaluatedTargetRow.status == "pending")
                    # All targets of one request share a ``created_at``, so add a
                    # stable ``id`` tiebreak: without it the drain order among a
                    # request's targets is nondeterministic and deferred roll-ups
                    # churn (children graded in an arbitrary order each cycle).
                    # The order also keeps a cascade's move targets (planned and
                    # claimed first, so lower ids) ahead of the roll-ups that
                    # depend on them, which is what stops a capacity-bounded
                    # drain from filling every slot with roll-ups that can only
                    # defer while their children wait for a slot.
                    .order_by(
                        EvaluatedTargetRow.created_at.asc(),
                        EvaluatedTargetRow.id.asc(),
                    )
                    .limit(limit)
                )
                if saturated_games:
                    stmt = stmt.where(
                        EvaluatedTargetRow.game_id.not_in(saturated_games)
                    )
                if dialect == "postgresql":
                    stmt = stmt.with_for_update(skip_locked=True)
                # ``_within_capacity`` stays the FINAL authority: the SQL filter
                # only removes games that were ALREADY saturated, while this
                # enforces the global cap and stops a game from exceeding its own
                # cap through rows claimed within this very batch.
                candidate_ids = _within_capacity(
                    list((await session.execute(stmt)).all()),
                    capacity=capacity,
                    per_game_limit=per_game_limit,
                    running_by_game=running_by_game,
                )
                if not candidate_ids:
                    return []
                now = utc_now()
                # Conditional transition keyed on the candidates AND still
                # ``pending``, with RETURNING so we get back exactly the rows
                # this transaction actually claimed (never rows a concurrent
                # claim/force-reset won). The conditional ``status='pending'``
                # filter is the at-most-once guard; SKIP LOCKED merely avoids
                # contention on Postgres.
                #
                # ``attempts`` is incremented BY the claim, so every returned row
                # already carries the epoch it was claimed at. The caller passes
                # that value back to its terminal write, which is what fences a
                # revoked claim out (see ``_running_under_claim``).
                claimed = list(
                    (
                        await session.execute(
                            update(EvaluatedTargetRow)
                            .where(
                                EvaluatedTargetRow.id.in_(candidate_ids),
                                EvaluatedTargetRow.status == "pending",
                            )
                            .values(
                                status="running",
                                attempts=EvaluatedTargetRow.attempts + 1,
                                updated_at=now,
                            )
                            .returning(EvaluatedTargetRow)
                        )
                    )
                    .scalars()
                    .all()
                )
                # Detach so callers hold a stable snapshot independent of this
                # (now-closing) session; no further ORM flush touches them.
                for row in claimed:
                    session.expunge(row)
                return claimed

    async def reclaim_stale_targets(
        self, *, lease_seconds: float, max_attempts: int
    ) -> ReclaimResult:
        """Give back the claims of workers that stopped reporting in.

        A claim is held by a row, not by a process, so a worker that is SIGKILLed
        mid-evaluation leaves its targets ``running`` forever — and because the
        concurrency cap counts ``running`` rows, those orphans permanently
        consume capacity until an operator intervenes. This is the sweep that
        makes a claim recoverable without one.

        Staleness is ``updated_at`` older than ``lease_seconds``. The lease
        measures *"is the worker alive?"*, not *"could this call still be
        running?"*, because a live worker heartbeats the targets it still owns
        (:meth:`heartbeat_targets`) — so a slow judge call is safe while its
        worker breathes, and the lease can be short enough for fast recovery.

        A target whose ``attempts`` has passed ``max_attempts`` is marked
        ``failed`` rather than reclaimed once more. A target that reliably kills
        its worker (an oversized prompt, a pathological timeline, an OOM) spends
        judge budget on every pass before crashing, so unbounded reclaim is both
        a money leak and a crashloop generator.

        Both statements run in ONE transaction so a concurrent claimer never sees
        a half-swept set.
        """
        # The cutoff is computed in Python and BOUND as a parameter rather than
        # expressed as database arithmetic (``now() - interval``), because
        # ``UtcDateTime`` stores a real ``timestamptz`` on Postgres and an ISO-8601
        # string on SQLite; a single piece of SQL date arithmetic cannot be right
        # on both. Bound this way the TypeDecorator renders the cutoff in each
        # dialect's own storage form, so the comparison is like-for-like: a
        # ``timestamptz`` compare on Postgres, and a lexicographic compare on
        # SQLite over fixed-width UTC ISO strings, whose byte order matches
        # chronological order.
        cutoff = utc_now() - timedelta(seconds=lease_seconds)
        async with self._session_factory() as session:
            async with session.begin():
                now = utc_now()
                failed = list(
                    (
                        await session.execute(
                            update(EvaluatedTargetRow)
                            .where(
                                EvaluatedTargetRow.status == "running",
                                EvaluatedTargetRow.updated_at < cutoff,
                                EvaluatedTargetRow.attempts > max_attempts,
                            )
                            .values(
                                status="failed",
                                error=(
                                    "abandoned claim: the worker holding this "
                                    "target stopped reporting and it has already "
                                    f"been attempted more than {max_attempts} "
                                    "times (see the attempts column); giving up "
                                    "rather than spending another judge call"
                                ),
                                updated_at=now,
                            )
                            .returning(EvaluatedTargetRow.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                # Explicitly bounded by ``max_attempts`` rather than relying on
                # the statement above having already moved the poison rows out of
                # ``running``: each statement then states its own rule and the
                # pair is order-independent.
                reclaimed = list(
                    (
                        await session.execute(
                            update(EvaluatedTargetRow)
                            .where(
                                EvaluatedTargetRow.status == "running",
                                EvaluatedTargetRow.updated_at < cutoff,
                                EvaluatedTargetRow.attempts <= max_attempts,
                            )
                            .values(status="pending", updated_at=now)
                            .returning(EvaluatedTargetRow.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                return ReclaimResult(
                    reclaimed_ids=tuple(reclaimed), failed_ids=tuple(failed)
                )

    async def heartbeat_targets(self, target_ids: Sequence[int]) -> int:
        """Refresh the lease on the targets a worker still owns. Returns the count.

        One UPDATE for the whole in-flight set, conditional on ``status='running'``
        so it can never RESURRECT a target that was cancelled, force-reset or
        reclaimed underneath the worker — those rows are simply not matched, and
        the worker's own terminal write is fenced separately by the epoch.

        An empty set issues no SQL at all: an idle worker beating once per cycle
        against the database would be pure noise.
        """
        if not target_ids:
            return 0
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(EvaluatedTargetRow)
                    .where(
                        EvaluatedTargetRow.id.in_(tuple(target_ids)),
                        EvaluatedTargetRow.status == "running",
                    )
                    .values(updated_at=utc_now())
                )
                return result.rowcount or 0

    async def cancel_request_targets(self, request_id: str) -> list[int]:
        """Mark all non-terminal targets of a request ``cancelled``, atomically.

        Returns the ids of the targets that were transitioned (was pending or
        running). A cancelled target keeps any prior ``verdict_json`` NULL: no
        verdict is written for it. Already-terminal targets are untouched, so
        cancelling a finished request is a no-op (returns an empty list).
        """
        async with self._session_factory() as session:
            async with session.begin():
                now = utc_now()
                rows = list(
                    (
                        await session.execute(
                            update(EvaluatedTargetRow)
                            .where(
                                EvaluatedTargetRow.request_id == request_id,
                                EvaluatedTargetRow.status.in_(("pending", "running")),
                            )
                            .values(
                                status="cancelled",
                                error="cancelled by request",
                                updated_at=now,
                            )
                            .returning(EvaluatedTargetRow.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                return rows

    async def ping(self) -> None:
        """Lightweight readiness probe: a trivial round-trip to the database."""
        async with self._session_factory() as session:
            await session.execute(text("SELECT 1"))
