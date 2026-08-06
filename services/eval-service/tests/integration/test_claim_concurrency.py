"""Claim concurrency against real PostgreSQL: the cap, the refill, the lease.

These live here rather than in ``tests/unit/`` because every one of them needs
two things running at once, and the unit fixture's shared-connection sqlite
database cannot isolate concurrent transactions -- run there, the same workloads
claim a target twice and strand rows in ``running``, which would be a test of the
fixture and not of the service. Real PostgreSQL is also the only place the
dialect-conditional machinery (``pg_advisory_xact_lock``, ``FOR UPDATE SKIP
LOCKED``) is exercised at all.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter
from typing import Any

import pytest
from sqlalchemy import func, select

from eval_service.config import Settings
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.worker import EvaluationWorker
from eval_service.storage.models import EvaluatedTargetRow
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    age_target_rows,
    agent_event,
    state_event,
)

pytestmark = pytest.mark.postgres

MOVE_PROMPT_SEQ = re.compile(r"single agent move \(seq (\d+)\)")


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        evaluator_version="eval-1",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
        # Short enough that a test can drive the sweep, still far apart enough to
        # satisfy the "lease must exceed the heartbeat" rule.
        eval_claim_lease_seconds=10.0,
        eval_claim_heartbeat_seconds=2.0,
    )
    base.update(overrides)
    return Settings(**base)


def _many_move_game(game_id: str, move_count: int):
    """One round holding ``move_count`` agent moves, closed by a terminal state."""
    events = [state_event(game_id=game_id, seq=1, round_number=0)]
    events += [
        agent_event(game_id=game_id, seq=seq, action="move_card")
        for seq in range(2, 2 + move_count)
    ]
    events.append(
        state_event(game_id=game_id, seq=2 + move_count, round_number=1, status="win")
    )
    return events


async def _enqueue_moves(repository, game_id: str, seqs: list[int], request_id: str):
    await repository.create_request(
        request_id=request_id,
        game_id=game_id,
        scope="move",
        selection={"seqs": seqs},
        force=False,
    )
    for seq in seqs:
        await repository.claim_target(
            request_id=request_id,
            game_id=game_id,
            target_seq=seq,
            scope="move",
            round_span=None,
            force=False,
        )


async def _count_running(repository) -> int:
    session_factory = repository._session_factory
    async with session_factory() as session:
        return (
            await session.scalar(
                select(func.count())
                .select_from(EvaluatedTargetRow)
                .where(EvaluatedTargetRow.status == "running")
            )
        ) or 0


async def _await_all_terminal(repository, request_id: str, *, deadline_seconds: float):
    """Poll until no target of ``request_id`` is pending or running.

    The poll interval is deliberately loose: a tighter one keeps the event loop
    busy issuing queries and starves the very worker being observed.
    """
    deadline = time.monotonic() + deadline_seconds
    targets: list[Any] = []
    while time.monotonic() < deadline:
        targets = await repository.list_targets_for_request(request_id)
        if targets and all(
            target.status not in ("pending", "running") for target in targets
        ):
            return targets
        await asyncio.sleep(0.02)
    statuses = Counter(target.status for target in targets)
    raise AssertionError(f"targets never reached a terminal status: {dict(statuses)}")


async def _stop(worker: EvaluationWorker, task: asyncio.Task) -> None:
    await worker.stop()
    await asyncio.wait_for(task, timeout=30)


# -- 8.1 the cap is a real bound --------------------------------------------


@pytest.mark.asyncio
async def test_concurrent_claimers_never_exceed_the_global_cap(
    postgres_repository_factory,
):
    """Claimers racing on separate connections must not overshoot the global cap.

    This is the test ``pg_advisory_xact_lock`` exists for. ``FOR UPDATE SKIP
    LOCKED`` locks the pending CANDIDATES; it does NOT lock the ``running`` rows
    that the capacity ``COUNT`` reads. Under READ COMMITTED, claim transactions
    that overlap each see the same pre-claim count and each spend the same
    capacity, so the global cap overshoots by up to the number of claimers. The
    claimed sets stay disjoint -- nothing is graded twice -- but the cap is
    documented as the guard against stampeding the provider, and a guard that
    multiplies when someone scales to two replicas is not a guard.

    Verified by mutation: with the advisory lock removed this test fails on
    every run -- both claimers take the full cap, 16 against a cap of 8 -- and
    passes on every run with it restored.

    THE SETUP IS LOAD-BEARING, and three details of it each had to be right
    before the race could be provoked at all:

    * **The backlog must exceed ``candidate_window * claimers`` (64 * 2).** The
      candidate SELECT takes ``FOR UPDATE SKIP LOCKED`` over a 64-row window, so
      with a small backlog the first claimer locks every pending row and the
      second finds nothing to skip to and claims zero. Overshoot needs every
      claimer to reach unlocked candidates of its own.
    * **The window must span more than one game.** With a single game the second
      claimer's per-game ``COUNT`` often lands after the first commits, the game
      reads as saturated, and it is excluded from the candidate SELECT -- so the
      per-game filter masks the global overshoot and the test passes for the
      wrong reason. The targets are therefore interleaved across two games.
    * **The pools must be warm.** A cold pool makes each claim's first statement
      wait on a TCP connect and a PostgreSQL handshake, which is slow enough that
      the claimers file past the capacity ``COUNT`` one at a time.

    Drafts missing any of these passed with the lock removed and proved nothing.
    """
    seed = await postgres_repository_factory()
    cap = 8
    per_game_cap = 4
    games = ("grace-a", "grace-b")
    seqs = list(range(2, 82))
    for game_id in games:
        await seed.create_request(
            request_id=f"r-{game_id}",
            game_id=game_id,
            scope="move",
            selection={"seqs": seqs},
            force=False,
        )
    # Interleaved so both games appear in every claimer's candidate window, and
    # 160 rows in total so both windows are full and disjoint.
    for seq in seqs:
        for game_id in games:
            await seed.claim_target(
                request_id=f"r-{game_id}",
                game_id=game_id,
                target_seq=seq,
                scope="move",
                round_span=None,
                force=False,
            )

    claimers = [await postgres_repository_factory() for _ in range(2)]
    await asyncio.gather(*(claimer.ping() for claimer in claimers))
    batches = await asyncio.gather(
        *(
            claimer.claim_pending_targets(global_limit=cap, per_game_limit=per_game_cap)
            for claimer in claimers
        )
    )

    claimed_ids = [target.id for batch in batches for target in batch]
    # The cap is a GLOBAL bound, not a per-claimer one.
    assert len(claimed_ids) <= cap, (
        f"the global cap of {cap} was overshot: "
        f"{[len(batch) for batch in batches]} claimed concurrently"
    )
    assert len(claimed_ids) > 0, "the race claimed nothing at all"
    # Disjoint: no target handed to two claimers.
    assert len(claimed_ids) == len(set(claimed_ids))
    # The per-game cap holds across the claimers for the same reason.
    per_game = Counter(target.game_id for batch in batches for target in batch)
    assert all(count <= per_game_cap for count in per_game.values())
    # And the database agrees with what the claimers were handed.
    assert await _count_running(seed) == len(claimed_ids)
    assert all(target.attempts == 1 for batch in batches for target in batch)


# -- 8.2 continuous refill ---------------------------------------------------


class ScriptedLatencyJudge(StubJudgeClient):
    """A judge whose latency follows a fixed straggler pattern.

    One slow call in four is the shape the replaced batch barrier handled worst:
    a freed slot waited for the SLOWEST member of its batch, so a single
    straggler idled the rest of the cap for its whole duration. It also records
    peak concurrency, the wall-clock window of every call, and which move each
    call graded, so the refill loop can be checked for its bound, for
    duplication, and for actually refilling.
    """

    def __init__(self, delays: list[float]):
        super().__init__()
        self._delays = tuple(delays)
        self._next_delay = 0
        self.in_flight = 0
        self.max_concurrent = 0
        self.seq_calls: Counter[int] = Counter()
        # (started, finished) per call, in start order.
        self.spans: list[list[float]] = []

    async def judge(self, *, model, messages, max_tokens, gateway_options=None) -> str:
        delay = self._delays[self._next_delay % len(self._delays)]
        self._next_delay += 1
        self.in_flight += 1
        self.max_concurrent = max(self.max_concurrent, self.in_flight)
        span = [time.monotonic(), 0.0]
        self.spans.append(span)
        try:
            prompt = " ".join(
                str(message.get("content", ""))
                for message in messages
                if isinstance(message, dict)
            )
            # Attribute by the prompt's own statement of what it grades: a move
            # prompt also carries its neighbours, so their arguments appear in it.
            match = MOVE_PROMPT_SEQ.search(prompt)
            assert match is not None, "a move prompt must name the seq it grades"
            self.seq_calls[int(match.group(1))] += 1
            await asyncio.sleep(delay)
            return await super().judge(
                model=model, messages=messages, max_tokens=max_tokens
            )
        finally:
            self.in_flight -= 1
            span[1] = time.monotonic()


@pytest.mark.asyncio
async def test_continuous_refill_grades_every_target_exactly_once(postgres_repository):
    """``run_forever`` refills freed slots without losing or duplicating work.

    The loop claims the moment any single evaluation finishes rather than waiting
    for its whole batch, which means claims, reclaim sweeps, heartbeats and
    terminal writes all overlap continuously. That is precisely the interleaving
    that could grade a target twice, so this asserts each of the invariants
    separately: every target terminal and completed, exactly one judge call per
    target, exactly one history write per target, ``attempts == 1`` everywhere
    (nothing was ever claimed a second time), and the per-game cap never
    exceeded.

    It also pins the refill itself: a target claimed after the first completion
    must START while the straggler is still in flight. That is exactly the
    property the batch barrier violated -- under it, no slot freed by a fast call
    could be refilled until the slowest member of the batch returned.
    """
    seqs = list(range(2, 26))  # 24 moves
    history = FakeHistoryClient({"grefill": _many_move_game("grefill", move_count=24)})
    judge = ScriptedLatencyJudge([0.40, 0.02, 0.02, 0.02])
    settings = _settings(eval_per_game_concurrency=4, eval_global_concurrency=8)
    worker = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=Evaluator(
            settings=settings,
            repository=postgres_repository,
            history=history,
            judge=judge,
        ),
        poll_interval_seconds=0.05,
    )
    await _enqueue_moves(postgres_repository, "grefill", seqs, "r-refill")

    task = asyncio.create_task(worker.run_forever())
    try:
        targets = await _await_all_terminal(
            postgres_repository, "r-refill", deadline_seconds=120
        )
    finally:
        await _stop(worker, task)

    assert len(targets) == len(seqs)
    assert {target.status for target in targets} == {"completed"}
    assert all(target.verdict_json is not None for target in targets)
    # Nothing claimed twice: a second claim would have moved the epoch.
    assert {target.attempts for target in targets} == {1}
    # Exactly one judge call and one history write-back per target.
    assert dict(judge.seq_calls) == {seq: 1 for seq in seqs}
    assert len(judge.calls) == len(seqs)
    assert sorted(e["payload"]["target_seq"] for _, e in history.written) == seqs
    # Genuinely parallel, and still bounded by the durable claim.
    assert judge.max_concurrent > 1
    assert judge.max_concurrent <= settings.eval_per_game_concurrency
    # Continuous refill: the first call is the 0.40s straggler, and at least one
    # later call both started after some earlier call had finished AND started
    # before the straggler returned. A batch barrier makes that set empty.
    straggler_started, straggler_finished = judge.spans[0]
    first_completion = min(finished for _started, finished in judge.spans)
    refilled = [
        started
        for started, _finished in judge.spans
        if first_completion < started < straggler_finished
    ]
    assert refilled, (
        "no evaluation started while the straggler was still running: the "
        "worker is waiting for the batch instead of refilling freed slots"
    )
    assert straggler_finished - straggler_started >= 0.4


# -- 8.3 reclaim -------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_worker_reclaims_and_completes_abandoned_claims(
    postgres_repository,
):
    """Claims orphaned by a dead worker are recovered with no operator action.

    The rows below are claimed and then simply abandoned -- exactly what a
    SIGKILLed replica leaves behind, and enough (with the caps counting
    ``running`` rows) to wedge all evaluation capacity indefinitely. A second
    worker's first cycle sweeps stale claims BEFORE it claims, so it picks the
    orphans up and grades them.
    """
    seqs = [2, 3, 4, 5]
    settings = _settings(eval_per_game_concurrency=4, eval_global_concurrency=8)
    history = FakeHistoryClient({"gorphan": _many_move_game("gorphan", move_count=4)})
    judge = StubJudgeClient()
    await _enqueue_moves(postgres_repository, "gorphan", seqs, "r-orphan")

    # Worker A claims everything and dies here.
    abandoned = await postgres_repository.claim_pending_targets(
        per_game_limit=4, global_limit=8
    )
    assert len(abandoned) == len(seqs)
    assert await _count_running(postgres_repository) == len(seqs)
    await age_target_rows(
        postgres_repository,
        [target.id for target in abandoned],
        seconds=settings.eval_claim_lease_seconds * 6,
    )

    worker_b = EvaluationWorker(
        settings=settings,
        repository=postgres_repository,
        history=history,
        evaluator=Evaluator(
            settings=settings,
            repository=postgres_repository,
            history=history,
            judge=judge,
        ),
        poll_interval_seconds=0.05,
    )
    task = asyncio.create_task(worker_b.run_forever())
    try:
        targets = await _await_all_terminal(
            postgres_repository, "r-orphan", deadline_seconds=60
        )
    finally:
        await _stop(worker_b, task)

    assert {target.status for target in targets} == {"completed"}
    assert all(target.verdict_json is not None for target in targets)
    # Reclaim leaves the epoch alone; the second worker's claim moves it, which
    # is what would have fenced the dead worker out had it come back.
    assert {target.attempts for target in targets} == {2}
    assert sorted(e["payload"]["target_seq"] for _, e in history.written) == seqs


# -- 8.4 epoch fencing across two workers ------------------------------------


class GatedJudge(StubJudgeClient):
    """A judge that parks mid-call until released, returning a marked verdict.

    Parking is what lets two workers be genuinely in flight on the same target at
    the same time, which is the only state in which the epoch guard does any
    work.
    """

    def __init__(self, *, overall_score: int):
        super().__init__()
        self.verdict = dict(self.verdict, overall_score=overall_score)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def judge(self, **kwargs) -> str:
        self.started.set()
        await self.release.wait()
        return await super().judge(**kwargs)


@pytest.mark.asyncio
async def test_a_reclaimed_targets_verdict_comes_from_the_new_owner(
    postgres_repository,
):
    """Two workers in flight on one target: only the current claim's write lands.

    Worker A is parked in its judge call when its claim ages out and is
    reclaimed; worker B takes the row and is parked in turn. A then returns to a
    row that IS ``running`` again -- so a status-only check passes, and the
    ``attempts`` epoch is the only thing standing between A's abandoned verdict
    and B's row. Both epoch guards are exercised here: the pre-write-back
    comparison that stops A emitting a history event at all, and the row-level
    fence on the terminal write. Without them the row ends up holding A's
    verdict marked ``completed`` while B's -- the one the reclaim was for -- is
    silently dropped.
    """
    settings = _settings(eval_per_game_concurrency=1, eval_global_concurrency=1)
    history = FakeHistoryClient({"gfence": _many_move_game("gfence", move_count=1)})
    stale_judge = GatedJudge(overall_score=1)
    fresh_judge = GatedJudge(overall_score=9)

    def _worker(judge: GatedJudge) -> EvaluationWorker:
        return EvaluationWorker(
            settings=settings,
            repository=postgres_repository,
            history=history,
            evaluator=Evaluator(
                settings=settings,
                repository=postgres_repository,
                history=history,
                judge=judge,
            ),
        )

    worker_a, worker_b = _worker(stale_judge), _worker(fresh_judge)
    await _enqueue_moves(postgres_repository, "gfence", [2], "r-fence")

    drain_a = asyncio.create_task(worker_a.drain_once())
    await asyncio.wait_for(stale_judge.started.wait(), timeout=10)
    targets = await postgres_repository.list_targets_for_request("r-fence")
    target_id = targets[0].id
    assert targets[0].status == "running"
    assert targets[0].attempts == 1

    # Worker A stops reporting in; its claim ages out and the sweep hands it back.
    await age_target_rows(
        postgres_repository,
        [target_id],
        seconds=settings.eval_claim_lease_seconds * 6,
    )
    reclaim = await postgres_repository.reclaim_stale_targets(
        lease_seconds=settings.eval_claim_lease_seconds, max_attempts=5
    )
    assert reclaim.reclaimed_ids == (target_id,)

    drain_b = asyncio.create_task(worker_b.drain_once())
    await asyncio.wait_for(fresh_judge.started.wait(), timeout=10)
    assert (await postgres_repository.get_target_by_id(target_id)).attempts == 2

    # A's judge finally returns, while B still owns the row.
    stale_judge.release.set()
    assert await asyncio.wait_for(drain_a, timeout=10) == 1
    fenced = await postgres_repository.get_target_by_id(target_id)
    assert fenced.status == "running", "the stale worker finalized a revoked claim"
    assert fenced.attempts == 2
    assert fenced.verdict_json is None

    fresh_judge.release.set()
    assert await asyncio.wait_for(drain_b, timeout=10) == 1
    owned = await postgres_repository.get_target_by_id(target_id)
    assert owned.status == "completed"
    assert owned.attempts == 2
    assert owned.verdict_json["overall_score"] == 9
    # Exactly one history event, and it is the OWNER's. The superseded worker
    # never reached the write-back at all, which matters because a history event
    # cannot be taken back: the row-level fence would have protected the target
    # but only AFTER a verdict nobody asked for had been emitted.
    assert len(history.written) == 1
    assert history.written[0][1]["payload"]["overall_score"] == 9
