from __future__ import annotations

import logging

import pytest

from history_service.config import Settings
from history_service.runtime.ingest import (
    ENVELOPE_FIELD,
    INGEST_RETRY_MAX_SECONDS,
    INGEST_RETRY_MIN_SECONDS,
    StreamIngester,
    decode_envelope_fields,
    encode_envelope_fields,
)
from history_service.storage.valkey import RespError

from .conftest import make_envelope


class FakeValkey:
    """Minimal in-process stand-in for a Valkey stream + consumer group."""

    def __init__(self, *, lag: int = 0):
        self._entries: list[tuple[str, list[str]]] = []
        self._delivered = 0
        self._acked: set[str] = set()
        self._lag = lag
        self._counter = 0

    def add(self, fields: list[str]) -> str:
        self._counter += 1
        entry_id = f"{self._counter}-0"
        self._entries.append((entry_id, fields))
        return entry_id

    async def execute(self, *parts):
        cmd = str(parts[0]).upper()
        if cmd == "XGROUP":
            return "OK"
        if cmd == "XREADGROUP":
            pending = self._entries[self._delivered :]
            if not pending:
                return None
            self._delivered = len(self._entries)
            return [[parts[-2], pending]]
        if cmd == "XACK":
            self._acked.add(parts[-1])
            return 1
        if cmd == "XINFO":
            return [["name", "history-service", "lag", self._lag]]
        if cmd == "PING":
            return "PONG"
        return None

    async def aclose(self):
        return None


class PELValkey:
    """Fake Valkey stream + consumer group that models a Pending Entries List.

    Unlike ``FakeValkey`` it tracks which delivered entries remain un-acked (the
    PEL) and their simulated idle time, so reclaim behaviour (XAUTOCLAIM) can be
    exercised deterministically.
    """

    def __init__(self):
        self._entries: dict[str, list[str]] = {}
        self._order: list[str] = []
        self._delivered = 0
        self._pending: dict[str, int] = {}
        self.acked: set[str] = set()
        self._counter = 0

    def add(self, fields: list[str]) -> str:
        self._counter += 1
        entry_id = f"{self._counter}-0"
        self._entries[entry_id] = fields
        self._order.append(entry_id)
        return entry_id

    def set_idle(self, entry_id: str, idle_ms: int) -> None:
        self._pending[entry_id] = idle_ms

    @property
    def pending(self) -> set[str]:
        return set(self._pending)

    async def execute(self, *parts):
        cmd = str(parts[0]).upper()
        if cmd == "XGROUP":
            return "OK"
        if cmd == "XREADGROUP":
            new = self._order[self._delivered :]
            self._delivered = len(self._order)
            if not new:
                return None
            for eid in new:
                self._pending[eid] = 0
            batch = [[eid, self._entries[eid]] for eid in new]
            return [[parts[-2], batch]]
        if cmd == "XACK":
            eid = parts[-1]
            self.acked.add(eid)
            self._pending.pop(eid, None)
            return 1
        if cmd == "XAUTOCLAIM":
            # XAUTOCLAIM stream group consumer min-idle start COUNT n
            min_idle = int(parts[4])
            claimable = sorted(
                eid for eid, idle in self._pending.items() if idle >= min_idle
            )
            for eid in claimable:
                self._pending[eid] = 0
            entries = [[eid, self._entries[eid]] for eid in claimable]
            return ["0-0", entries, []]
        if cmd == "XINFO":
            return [["name", "history-service", "lag", 0]]
        return None

    async def aclose(self):
        return None


class ReclaimFailsValkey(PELValkey):
    """PELValkey whose XAUTOCLAIM dies the way a reset connection dies.

    A ``ConnectionResetError`` rather than a ``RespError``: a transport failure is
    not a server reply, so it must not be mistaken for the "unknown command"
    signal that triggers the XPENDING fallback.
    """

    def __init__(self):
        super().__init__()
        self.autoclaim_attempts = 0

    async def execute(self, *parts):
        if str(parts[0]).upper() == "XAUTOCLAIM":
            self.autoclaim_attempts += 1
            raise ConnectionResetError(104, "Connection reset by peer")
        return await super().execute(*parts)


class NoAutoclaimValkey(PELValkey):
    """PELValkey whose server predates XAUTOCLAIM (forces the XPENDING fallback)."""

    async def execute(self, *parts):
        cmd = str(parts[0]).upper()
        if cmd == "XAUTOCLAIM":
            raise RespError("ERR unknown command 'XAUTOCLAIM'")
        if cmd == "XPENDING":
            # XPENDING stream group IDLE min-idle - + count
            min_idle = int(parts[4])
            rows = [
                [eid, "consumer", idle, 1]
                for eid, idle in self._pending.items()
                if idle >= min_idle
            ]
            return rows or None
        if cmd == "XCLAIM":
            # XCLAIM stream group consumer min-idle id [id ...]
            entries = []
            for eid in parts[5:]:
                if eid in self._entries:
                    self._pending[eid] = 0
                    entries.append([eid, self._entries[eid]])
            return entries
        return await super().execute(*parts)


class FlakyRepository:
    """Wraps a real repository, raising once per chosen producer offset."""

    def __init__(self, inner, *, fail_offsets):
        self._inner = inner
        self._fail_offsets = set(fail_offsets)
        self.commit_calls: list = []

    async def commit_event(self, envelope):
        self.commit_calls.append(envelope.producer_offset)
        if envelope.producer_offset in self._fail_offsets:
            self._fail_offsets.discard(envelope.producer_offset)
            raise RuntimeError("transient commit failure")
        return await self._inner.commit_event(envelope)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class RecordingSnapshots:
    """Records maybe_snapshot_best_effort calls from the ingester."""

    def __init__(self, *, fail: bool = False):
        self.calls: list[tuple[str, int, str]] = []
        self._fail = fail

    async def maybe_snapshot_best_effort(
        self, game_id, current_seq, platform="dragncards"
    ):
        self.calls.append((game_id, current_seq, platform))
        return None


def test_envelope_roundtrip_on_stream():
    env = make_envelope("g1", producer_offset=7, actor="agent", event_type="move")
    fields = encode_envelope_fields(env)
    assert fields[0] == ENVELOPE_FIELD
    decoded = decode_envelope_fields(fields)
    assert decoded.game_id == "g1"
    assert decoded.producer_offset == 7
    assert decoded.actor == "agent"


@pytest.mark.asyncio
async def test_ingester_persists_and_acks(repository):
    valkey = FakeValkey()
    valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=1)))
    ingester = StreamIngester(settings=Settings(), repository=repository, client=valkey)
    await ingester.ensure_group()
    processed = await ingester.process_batch()
    assert processed == 2
    events = await repository.list_events("g1")
    assert [e.seq for e in events] == [1, 2]
    assert valkey._acked == {"1-0", "2-0"}


@pytest.mark.asyncio
async def test_ingester_invokes_snapshot_after_commit(repository):
    """The production ingest path evaluates snapshot cadence after each commit."""
    valkey = FakeValkey()
    valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=1)))
    snapshots = RecordingSnapshots()
    ingester = StreamIngester(
        settings=Settings(),
        repository=repository,
        client=valkey,
        snapshots=snapshots,
    )
    await ingester.ensure_group()
    await ingester.process_batch()
    # One snapshot evaluation per inserted event, addressed by game_id + seq.
    assert snapshots.calls == [
        ("g1", 1, "dragncards"),
        ("g1", 2, "dragncards"),
    ]


@pytest.mark.asyncio
async def test_ingester_forwards_event_platform_to_snapshot(repository):
    valkey = FakeValkey()
    envelope = make_envelope("marvel-game", producer_offset=0).model_copy(
        update={"platform": "marvel-lcg"}
    )
    valkey.add(encode_envelope_fields(envelope))
    snapshots = RecordingSnapshots()
    ingester = StreamIngester(
        settings=Settings(),
        repository=repository,
        client=valkey,
        snapshots=snapshots,
    )
    await ingester.ensure_group()
    await ingester.process_batch()

    assert snapshots.calls == [("marvel-game", 1, "marvel-lcg")]


@pytest.mark.asyncio
async def test_ingester_snapshot_not_called_for_duplicate(repository):
    """A deduped (non-inserted) commit does not trigger a snapshot evaluation."""
    valkey = FakeValkey()
    dup = encode_envelope_fields(make_envelope("g1", producer_offset=0))
    valkey.add(dup)
    valkey.add(dup)
    snapshots = RecordingSnapshots()
    ingester = StreamIngester(
        settings=Settings(),
        repository=repository,
        client=valkey,
        snapshots=snapshots,
    )
    await ingester.ensure_group()
    await ingester.process_batch()
    assert snapshots.calls == [("g1", 1, "dragncards")]


@pytest.mark.asyncio
async def test_ingester_duplicate_stored_once(repository):
    valkey = FakeValkey()
    dup = encode_envelope_fields(make_envelope("g1", producer_offset=0))
    valkey.add(dup)
    valkey.add(dup)  # at-least-once duplicate
    ingester = StreamIngester(settings=Settings(), repository=repository, client=valkey)
    await ingester.ensure_group()
    await ingester.process_batch()
    events = await repository.list_events("g1")
    assert len(events) == 1
    # Both deliveries acked even though only one row was written.
    assert len(valkey._acked) == 2


@pytest.mark.asyncio
async def test_ingester_drops_malformed_entry(repository):
    valkey = FakeValkey()
    valkey.add([ENVELOPE_FIELD, "{not json"])
    valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    ingester = StreamIngester(settings=Settings(), repository=repository, client=valkey)
    await ingester.ensure_group()
    await ingester.process_batch()
    assert len(await repository.list_events("g1")) == 1
    assert len(valkey._acked) == 2  # malformed entry acked, not wedged


class RecordingLagSink:
    def __init__(self):
        self.signals = []

    async def emit_consumer_lag(self, stream, group, lag):
        self.signals.append((stream, group, lag))


@pytest.mark.asyncio
async def test_lag_signal_emitted_over_threshold(repository):
    valkey = FakeValkey(lag=5000)
    sink = RecordingLagSink()
    ingester = StreamIngester(
        settings=Settings(history_consumer_lag_alert_threshold=1000),
        repository=repository,
        client=valkey,
        lag_sink=sink,
    )
    await ingester.ensure_group()
    await ingester.process_batch()
    assert sink.signals == [("history:ingest", "history-service", 5000)]


@pytest.mark.asyncio
async def test_lag_signal_not_emitted_under_threshold(repository):
    valkey = FakeValkey(lag=10)
    sink = RecordingLagSink()
    ingester = StreamIngester(
        settings=Settings(history_consumer_lag_alert_threshold=1000),
        repository=repository,
        client=valkey,
        lag_sink=sink,
    )
    await ingester.ensure_group()
    await ingester.process_batch()
    assert sink.signals == []


@pytest.mark.asyncio
async def test_commit_failure_isolated_and_left_pending(repository):
    """One entry's transient commit failure must not lose the rest of the batch.

    The failed entry stays un-acked (pending) for a later reclaim, while its
    siblings still commit and get acked.
    """
    valkey = PELValkey()
    e0 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    e1 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=1)))
    e2 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=2)))
    flaky = FlakyRepository(repository, fail_offsets={1})
    ingester = StreamIngester(settings=Settings(), repository=flaky, client=valkey)
    await ingester.ensure_group()

    processed = await ingester.process_batch()

    # Every entry in the batch was attempted; the failure did not abort it.
    assert processed == 3
    # The two healthy entries committed and were acknowledged.
    events = await repository.list_events("g1")
    assert [e.producer_offset for e in events] == [0, 2]
    assert valkey.acked == {e0, e2}
    # The failed entry is NOT acked and remains pending for reclaim.
    assert e1 not in valkey.acked
    assert e1 in valkey.pending


@pytest.mark.asyncio
async def test_stale_pending_entries_reclaimed_on_later_cycle(repository):
    """Entries left pending after a failure are reclaimed and committed later."""
    valkey = PELValkey()
    e0 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    e1 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=1)))
    flaky = FlakyRepository(repository, fail_offsets={0, 1})
    ingester = StreamIngester(settings=Settings(), repository=flaky, client=valkey)
    await ingester.ensure_group()

    # First cycle: both commits fail, so both entries stay pending, un-acked.
    await ingester.process_batch()
    assert await repository.list_events("g1") == []
    assert valkey.pending == {e0, e1}
    assert valkey.acked == set()

    # They age past the claim min-idle window.
    valkey.set_idle(e0, 60_000)
    valkey.set_idle(e1, 60_000)

    # Second cycle: reclaim_pending claims them and the retry now commits.
    await ingester.process_batch()
    events = await repository.list_events("g1")
    assert [e.producer_offset for e in events] == [0, 1]
    assert valkey.acked == {e0, e1}
    assert valkey.pending == set()


@pytest.mark.asyncio
async def test_reclaim_falls_back_to_xpending_xclaim(repository):
    """When the server lacks XAUTOCLAIM, reclaim uses XPENDING + XCLAIM."""
    valkey = NoAutoclaimValkey()
    e0 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    flaky = FlakyRepository(repository, fail_offsets={0})
    ingester = StreamIngester(settings=Settings(), repository=flaky, client=valkey)
    await ingester.ensure_group()

    # First cycle: commit fails, entry left pending.
    await ingester.process_batch()
    assert valkey.pending == {e0}
    assert valkey.acked == set()

    valkey.set_idle(e0, 60_000)

    # Second cycle: fallback reclaim path recovers and commits the entry.
    await ingester.process_batch()
    events = await repository.list_events("g1")
    assert [e.producer_offset for e in events] == [0]
    assert valkey.acked == {e0}
    assert valkey.pending == set()


async def test_reclaim_failure_does_not_discard_the_batch(repository, caplog):
    """A transport failure while reclaiming must not cost us the new entries.

    Regression pin for DRA-35. ``reclaim_pending`` runs first in ``process_batch``,
    so its failure used to abort the whole batch before ``XREADGROUP`` ever ran.
    Nothing was ingested, the poll loop retried in a hot cycle, and a transient
    Valkey blip became an unbounded error flood. Reclaiming is best-effort -- the
    entries it would have claimed stay pending and are retried next cycle -- so it
    must degrade to a warning rather than take the batch down with it.
    """
    valkey = ReclaimFailsValkey()
    e0 = valkey.add(encode_envelope_fields(make_envelope("g1", producer_offset=0)))
    ingester = StreamIngester(settings=Settings(), repository=repository, client=valkey)
    await ingester.ensure_group()

    with caplog.at_level(logging.WARNING):
        processed = await ingester.process_batch()

    # The new entry was read, committed and acked despite the reclaim failure.
    assert processed == 1
    assert [e.producer_offset for e in await repository.list_events("g1")] == [0]
    assert valkey.acked == {e0}
    assert valkey.autoclaim_attempts == 1
    # The failure is reported, but as a one-line warning rather than a traceback.
    assert any("Reclaiming pending entries failed" in r.message for r in caplog.records)
    assert not any(r.exc_info for r in caplog.records)


async def test_run_forever_backs_off_and_logs_one_traceback_per_outage(
    repository, caplog, monkeypatch
):
    """A sustained failure must back off and stop re-logging the same traceback.

    Regression pin for DRA-35, whose complaint was log volume: the loop retried on
    a fixed 500ms delay and called ``logger.exception`` every time, so a Valkey
    outage emitted a full stack roughly twice a second for as long as it lasted.
    """
    valkey = PELValkey()
    ingester = StreamIngester(settings=Settings(), repository=repository, client=valkey)

    async def always_fails() -> int:
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr(ingester, "process_batch", always_fails)

    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)
        if len(delays) >= 6:
            ingester._running = False

    monkeypatch.setattr("history_service.runtime.ingest.asyncio.sleep", fake_sleep)

    with caplog.at_level(logging.INFO):
        await ingester.run_forever()

    # The delay grows instead of pinning the loop at 500ms forever.
    assert delays[0] == INGEST_RETRY_MIN_SECONDS
    assert delays == sorted(delays)
    assert delays[-1] > delays[0]
    assert all(d <= INGEST_RETRY_MAX_SECONDS for d in delays)

    # Exactly one traceback for the whole outage; the rest carry a running count.
    with_tracebacks = [r for r in caplog.records if r.exc_info]
    assert len(with_tracebacks) == 1
    assert "Ingest batch failed" in with_tracebacks[0].message
    assert sum("still failing" in r.message for r in caplog.records) == len(delays) - 1
