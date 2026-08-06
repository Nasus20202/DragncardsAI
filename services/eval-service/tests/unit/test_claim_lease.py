"""The claim epoch, the claim lease, and the fairness of the candidate window.

Everything here drives the repository SEQUENTIALLY on the sqlite fixture. The
concurrency properties these mechanisms exist for -- two claimers racing, a
worker refilling continuously -- are proven in ``tests/integration/`` against
real PostgreSQL, because the shared-connection sqlite fixture cannot isolate
concurrent transactions (see the ``repository`` fixture docstring).
"""

from __future__ import annotations

import logging

import pytest

from eval_service.config import Settings
from eval_service.runtime.evaluator import Evaluator
from eval_service.runtime.worker import EvaluationWorker
from tests.unit.conftest import (
    FakeHistoryClient,
    StubJudgeClient,
    age_target_rows,
    agent_event,
    state_event,
)

# The lease every test here ages rows against. A plain constant rather than the
# settings default, so a later change to the default cannot silently turn one of
# these into a test of nothing.
LEASE_SECONDS = 120.0


def _settings(**overrides):
    base = dict(
        eval_judge_model="anthropic/claude-x",
        eval_max_attempts=1,
        eval_retry_backoff_seconds=0.0,
    )
    base.update(overrides)
    return Settings(**base)


def _game(game_id: str, move_count: int):
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


async def _revoke_claim(repository, target_id: int) -> None:
    """Age a live claim past the lease and let the sweep hand the row back."""
    await age_target_rows(repository, [target_id], seconds=LEASE_SECONDS * 2)
    result = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=5
    )
    assert result.reclaimed_ids == (target_id,)


# -- epoch fencing ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_revoked_claims_terminal_write_is_fenced_out(repository):
    """A worker whose claim was revoked cannot write over the new claim's row.

    ``status='running'`` alone answers "is this row running?", never "is it still
    running under MY claim?" -- so once the row is reclaimed and taken by a
    second worker, the first worker's late verdict would pass a status-only guard
    and overwrite work the user actually asked for. The ``attempts`` epoch is
    what makes that write match no rows.
    """
    await _enqueue_moves(repository, "g1", [2], "r1")
    first = await repository.claim_pending_targets()
    target_id, stale_epoch = first[0].id, first[0].attempts
    assert stale_epoch == 1

    await _revoke_claim(repository, target_id)
    second = await repository.claim_pending_targets()
    assert [t.id for t in second] == [target_id]
    assert second[0].attempts == 2

    # The first worker's judge call finally returns. Every durable write it can
    # still make carries the epoch it was claimed at, and every one is discarded.
    await repository.finalize_completed(target_id, {"overall_score": 1}, attempts=1)
    await repository.mark_failed(target_id, "stale worker gave up", attempts=1)
    await repository.mark_skipped(target_id, "stale worker skipped", attempts=1)
    assert (
        await repository.record_attempt_error(target_id, "stale error", attempts=1)
        is False
    )
    assert await repository.defer_to_pending(target_id, attempts=1) is False

    row = await repository.get_target_by_id(target_id)
    # The row keeps the NEWER claim's state, untouched by any of the above.
    assert row.status == "running"
    assert row.attempts == 2
    assert row.verdict_json is None
    assert row.error is None


@pytest.mark.asyncio
async def test_the_current_claims_terminal_write_still_lands(repository):
    """The fence rejects revoked claims ONLY; the owning claim completes normally.

    Without this half, a guard that rejected every terminal write would satisfy
    the fencing test above while breaking the service outright.
    """
    await _enqueue_moves(repository, "g1", [2], "r1")
    first = await repository.claim_pending_targets()
    target_id = first[0].id

    await _revoke_claim(repository, target_id)
    second = await repository.claim_pending_targets()
    current_epoch = second[0].attempts
    assert current_epoch == 2

    await repository.finalize_completed(
        target_id, {"overall_score": 9}, attempts=current_epoch
    )

    row = await repository.get_target_by_id(target_id)
    assert row.status == "completed"
    assert row.attempts == current_epoch
    assert row.verdict_json == {"overall_score": 9}


# -- the lease --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_claim_aged_past_the_lease_returns_to_pending(repository):
    """An abandoned claim is given back and can be claimed again.

    The claim is held by a row, not by a process, so nothing but the lease sweep
    can notice that the worker holding it stopped existing.
    """
    await _enqueue_moves(repository, "g1", [2], "r1")
    claimed = await repository.claim_pending_targets()
    target_id = claimed[0].id
    # Still inside the lease: a live claim is not up for grabs.
    untouched = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=5
    )
    assert untouched.reclaimed_ids == ()
    assert (await repository.get_target_by_id(target_id)).status == "running"

    assert (
        await age_target_rows(repository, [target_id], seconds=LEASE_SECONDS * 2) == 1
    )
    result = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=5
    )
    assert result.reclaimed_ids == (target_id,)
    assert result.failed_ids == ()
    assert (await repository.get_target_by_id(target_id)).status == "pending"

    reclaimed = await repository.claim_pending_targets()
    assert [t.id for t in reclaimed] == [target_id]
    # The re-claim moves the epoch, which is what fences the dead worker out.
    assert reclaimed[0].attempts == 2


@pytest.mark.asyncio
async def test_reclaim_releases_capacity_wedged_by_abandoned_claims(repository):
    """REGRESSION PIN for the deadlock this change exists to fix.

    The concurrency cap is computed from the rows recorded ``running``, so
    targets left ``running`` by a worker that died mid-evaluation consume that
    capacity forever: every later claim returns empty, evaluation never resumes,
    and before this change the only way out was an operator editing the table.
    The lease sweep is that way out, and this test fails the moment it stops
    working.
    """
    settings = _settings()
    cap = settings.eval_global_concurrency
    await _enqueue_moves(repository, "g1", list(range(2, 2 + cap + 4)), "r1")

    abandoned = await repository.claim_pending_targets(
        global_limit=cap, per_game_limit=cap
    )
    assert len(abandoned) == cap
    # Their worker dies here. Nothing will ever finalize these rows.
    assert (
        await repository.claim_pending_targets(global_limit=cap, per_game_limit=cap)
        == []
    ), "capacity is wedged by the orphaned claims -- this is the bug"

    abandoned_ids = [t.id for t in abandoned]
    assert (
        await age_target_rows(repository, abandoned_ids, seconds=LEASE_SECONDS * 2)
        == cap
    )
    result = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=settings.eval_max_attempts
    )
    assert set(result.reclaimed_ids) == set(abandoned_ids)
    assert result.failed_ids == ()

    recovered = await repository.claim_pending_targets(
        global_limit=cap, per_game_limit=cap
    )
    assert len(recovered) == cap
    # And it is the wedged rows themselves that came back, at a fresh epoch.
    assert {t.id for t in recovered} == set(abandoned_ids)
    assert {t.attempts for t in recovered} == {2}


@pytest.mark.asyncio
async def test_a_target_past_max_attempts_is_failed_not_reclaimed_again(repository):
    """A poison target is given up on instead of being retried forever.

    A target that reliably kills its worker spends judge budget on every pass
    before crashing, so unbounded reclaim is a money leak and a crashloop
    generator at once. Past ``max_attempts`` the sweep marks it ``failed`` with
    the reason instead of handing it to yet another worker.
    """
    await _enqueue_moves(repository, "g1", [2], "r1")
    first = await repository.claim_pending_targets()
    target_id = first[0].id
    assert first[0].attempts == 1

    # One reclaim is allowed at max_attempts=1: attempts (1) has not passed it.
    await age_target_rows(repository, [target_id], seconds=LEASE_SECONDS * 2)
    retried = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=1
    )
    assert retried.reclaimed_ids == (target_id,)
    assert retried.failed_ids == ()

    second = await repository.claim_pending_targets()
    assert second[0].attempts == 2
    await age_target_rows(repository, [target_id], seconds=LEASE_SECONDS * 2)
    given_up = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=1
    )
    assert given_up.failed_ids == (target_id,)
    assert given_up.reclaimed_ids == ()

    row = await repository.get_target_by_id(target_id)
    assert row.status == "failed"
    # A bare ``failed`` with no reason would leave an operator guessing.
    assert row.error
    assert "attempts" in row.error
    # Terminal means terminal: it is not offered to a worker again.
    assert await repository.claim_pending_targets() == []


@pytest.mark.asyncio
async def test_a_heartbeaten_claim_outlives_the_lease(repository):
    """A live worker's slow evaluation is never reclaimed out from under it.

    This is what lets the lease be short. Because the worker refreshes the
    targets it still owns, the lease measures "is the worker alive?" rather than
    "could this judge call still be running?" -- so an evaluation older than the
    whole lease window stays put as long as its owner keeps reporting in.
    """
    await _enqueue_moves(repository, "g1", [2], "r1")
    claimed = await repository.claim_pending_targets()
    target_id = claimed[0].id

    # The claim was taken longer ago than the lease...
    await age_target_rows(repository, [target_id], seconds=LEASE_SECONDS * 2)
    # ...but its owner is alive and says so.
    assert await repository.heartbeat_targets([target_id]) == 1

    result = await repository.reclaim_stale_targets(
        lease_seconds=LEASE_SECONDS, max_attempts=5
    )
    assert result.reclaimed_ids == ()
    assert result.failed_ids == ()
    row = await repository.get_target_by_id(target_id)
    assert row.status == "running"
    assert row.attempts == 1


@pytest.mark.asyncio
async def test_the_heartbeat_cannot_resurrect_a_target_it_no_longer_owns(repository):
    """A cancelled target stays cancelled even if its old worker beats for it.

    The heartbeat is conditional on ``status='running'``, so a row that was
    cancelled, force-reset or reclaimed underneath the worker is simply not
    matched -- otherwise a beat would keep a dead claim's lease alive forever.
    """
    await _enqueue_moves(repository, "g1", [2], "r1")
    claimed = await repository.claim_pending_targets()
    target_id = claimed[0].id
    assert await repository.cancel_request_targets("r1") == [target_id]

    assert await repository.heartbeat_targets([target_id]) == 0
    assert (await repository.get_target_by_id(target_id)).status == "cancelled"


@pytest.mark.asyncio
async def test_a_failing_reclaim_logs_a_warning_and_the_cycle_continues(
    repository, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """A database blip during the sweep must not abort the worker's cycle.

    Letting it abort turns a transient failure into a hot loop: the claim never
    runs, the loop retries immediately, and the service spins on the database.
    So the sweep is best-effort -- a warning, and the same cycle goes on to
    claim and evaluate.
    """
    seqs = [2, 3, 4]
    history = FakeHistoryClient({"g1": _game("g1", move_count=3)})
    judge = StubJudgeClient()
    settings = _settings(eval_per_game_concurrency=4, eval_global_concurrency=8)
    worker = EvaluationWorker(
        settings=settings,
        repository=repository,
        history=history,
        evaluator=Evaluator(
            settings=settings, repository=repository, history=history, judge=judge
        ),
    )
    await _enqueue_moves(repository, "g1", seqs, "r1")

    async def boom(**_kwargs):
        raise RuntimeError("connection reset by peer")

    monkeypatch.setattr(repository, "reclaim_stale_targets", boom)

    with caplog.at_level(logging.WARNING, logger="eval_service.runtime.worker"):
        # No exception escapes the maintenance step...
        await worker._maintain()
        # ...and the rest of the cycle runs, which is the whole point.
        progressed = await worker.drain_once()

    assert progressed == len(seqs)
    targets = await repository.list_targets_for_request("r1")
    assert {t.status for t in targets} == {"completed"}

    failures = [
        record
        for record in caplog.records
        if "Reclaiming stale claims failed" in record.getMessage()
    ]
    assert len(failures) == 1
    assert failures[0].levelno == logging.WARNING
    # A warning, not a traceback: a transient blip is not an incident.
    assert failures[0].exc_info is None
    assert "connection reset by peer" in failures[0].getMessage()


# -- fairness of the candidate window ---------------------------------------


@pytest.mark.asyncio
async def test_a_saturated_game_does_not_starve_another_games_targets(repository):
    """A saturated game's backlog must not consume the whole candidate window.

    Candidates are windowed by ``limit``. One whole-game request can leave far
    more pending rows for a single game than that window holds, so once that game
    hits its per-game cap, a window taken over ALL pending rows contains nothing
    but its rows -- every candidate is dropped, the claim returns empty, and a
    second game's targets are never even considered while global capacity sits
    idle. The saturated game is therefore excluded in SQL, BEFORE the window is
    taken.

    The backlog below (8 rows) is deliberately larger than ``limit`` (4): with a
    Python-side filter this claim returns nothing at all.
    """
    await _enqueue_moves(repository, "g-busy", list(range(2, 12)), "r-busy")
    saturating = await repository.claim_pending_targets(
        limit=4, per_game_limit=2, global_limit=8
    )
    assert [t.game_id for t in saturating] == ["g-busy", "g-busy"]

    # A second user's game arrives behind the first game's backlog.
    await _enqueue_moves(repository, "g-waiting", [2, 3], "r-waiting")

    claimed = await repository.claim_pending_targets(
        limit=4, per_game_limit=2, global_limit=8
    )
    assert [t.game_id for t in claimed] == ["g-waiting", "g-waiting"]
    # And the saturated game keeps exactly the slots it already held.
    busy = await repository.list_targets_for_request("r-busy")
    assert sum(1 for t in busy if t.status == "running") == 2
