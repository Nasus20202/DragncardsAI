from __future__ import annotations

from dataclasses import dataclass
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
                await session.execute(
                    update(EvaluatedTargetRow)
                    .where(EvaluatedTargetRow.id == row.id)
                    .values(
                        request_id=request_id,
                        status="pending",
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

    async def finalize_completed(self, target_id: int, verdict: dict[str, Any]) -> None:
        await self._transition_running(
            target_id, status="completed", verdict_json=verdict, error=None
        )

    async def mark_skipped(self, target_id: int, error: str) -> None:
        """Record a DELIBERATE skip (a non-strategic action) with its reason.

        Reserved for "there was no decision to grade here". A failure uses
        ``mark_failed`` so a client can tell an error apart from a designed skip.
        """
        await self._transition_running(
            target_id, status="skipped", error=sanitize_error_detail(error)
        )

    async def mark_failed(self, target_id: int, error: str) -> None:
        await self._transition_running(
            target_id, status="failed", error=sanitize_error_detail(error)
        )

    async def record_attempt_error(self, target_id: int, error: str) -> bool:
        """Record a mid-evaluation failure on a target that is still ``running``.

        A judge attempt that failed and will be retried is detail the user must be
        able to read WHILE the evaluation continues, so it is written to Postgres
        rather than held in the worker — any poller or stream then reads it from
        the authoritative snapshot. The status is left untouched (the target is
        still being worked on), and the ``status='running'`` guard means a
        concurrent cancel or force re-claim is never clobbered. Returns whether a
        row was actually updated.
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(EvaluatedTargetRow)
                    .where(
                        EvaluatedTargetRow.id == target_id,
                        EvaluatedTargetRow.status == "running",
                    )
                    .values(error=sanitize_error_detail(error), updated_at=utc_now())
                )
                return (result.rowcount or 0) > 0

    async def _transition_running(self, target_id: int, **values: Any) -> None:
        """Move a target out of ``running`` to a terminal state, conditionally.

        The ``status='running'`` guard means a concurrent force re-claim (which
        resets the row to ``pending`` under a NEW claim) is never clobbered by a
        stale worker finalizing the prior evaluation: the UPDATE simply matches
        no rows and is a no-op.
        """
        async with self._session_factory() as session:
            async with session.begin():
                values["updated_at"] = utc_now()
                await session.execute(
                    update(EvaluatedTargetRow)
                    .where(
                        EvaluatedTargetRow.id == target_id,
                        EvaluatedTargetRow.status == "running",
                    )
                    .values(**values)
                )

    async def defer_to_pending(self, target_id: int) -> bool:
        """Reset a ``running`` target back to ``pending`` so a later drain retries.

        Used to gate a higher-level (round/game) target while the lower-level
        children it depends on are still being graded: the roll-up is re-queued
        rather than produced against incomplete child context. The
        ``status='running'`` guard means a concurrent cancel / force re-claim is
        never clobbered. Returns whether a row was actually re-deferred.
        """
        async with self._session_factory() as session:
            async with session.begin():
                result = await session.execute(
                    update(EvaluatedTargetRow)
                    .where(
                        EvaluatedTargetRow.id == target_id,
                        EvaluatedTargetRow.status == "running",
                    )
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
        self, *, limit: int = 64
    ) -> list[EvaluatedTargetRow]:
        """Atomically claim pending targets and transition them to ``running``.

        Returns ONLY the targets this caller successfully claimed, so two
        replicas draining concurrently never both pick the same row (the
        design's at-most-once-per-replica guarantee). Pending state lives
        durably in Postgres (no in-memory queue), so a restart resumes work.

        On PostgreSQL the candidate rows are locked with ``FOR UPDATE SKIP
        LOCKED`` so concurrent drainers select disjoint sets; on SQLite (tests)
        the same transaction serializes claims, so the lock clause is omitted
        and the conditional ``status='pending'`` UPDATE is the at-most-once
        guard.
        """
        async with self._session_factory() as session:
            async with session.begin():
                dialect = session.bind.dialect.name
                stmt = (
                    select(EvaluatedTargetRow.id)
                    .where(EvaluatedTargetRow.status == "pending")
                    # All targets of one request share a ``created_at``, so add a
                    # stable ``id`` tiebreak: without it the drain order among a
                    # request's targets is nondeterministic and deferred roll-ups
                    # churn (children graded in an arbitrary order each cycle).
                    .order_by(
                        EvaluatedTargetRow.created_at.asc(),
                        EvaluatedTargetRow.id.asc(),
                    )
                    .limit(limit)
                )
                if dialect == "postgresql":
                    stmt = stmt.with_for_update(skip_locked=True)
                candidate_ids = list((await session.execute(stmt)).scalars().all())
                if not candidate_ids:
                    return []
                now = utc_now()
                # Conditional transition keyed on the candidates AND still
                # ``pending``, with RETURNING so we get back exactly the rows
                # this transaction actually claimed (never rows a concurrent
                # claim/force-reset won). The conditional ``status='pending'``
                # filter is the at-most-once guard; SKIP LOCKED merely avoids
                # contention on Postgres.
                claimed = list(
                    (
                        await session.execute(
                            update(EvaluatedTargetRow)
                            .where(
                                EvaluatedTargetRow.id.in_(candidate_ids),
                                EvaluatedTargetRow.status == "pending",
                            )
                            .values(status="running", updated_at=now)
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
