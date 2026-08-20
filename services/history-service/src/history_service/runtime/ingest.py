from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

from pydantic import ValidationError

from history_service.config import Settings
from history_service.runtime.snapshots import SnapshotService
from history_service.schemas.envelope import EventEnvelope
from history_service.storage.repository import CommitResult, Repository
from history_service.storage.valkey import RespConnection, RespError
from history_service.telemetry import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

ENVELOPE_FIELD = "envelope_json"

# Retry pacing for the poll loop when a whole batch fails. The floor matches the
# original fixed delay; the ceiling stops a sustained Valkey outage from spinning
# the loop (and the log) several times a second indefinitely (DRA-35).
INGEST_RETRY_MIN_SECONDS = 0.5
INGEST_RETRY_MAX_SECONDS = 30.0


def _is_unknown_command(exc: RespError) -> bool:
    """True when a RESP error indicates the server does not know the command.

    Older Valkey/Redis builds predate ``XAUTOCLAIM``; they answer with an
    ``ERR unknown command`` reply, which is our signal to fall back to
    ``XPENDING`` + ``XCLAIM``.
    """
    return "unknown command" in str(exc).lower()


class StreamClient(Protocol):
    async def execute(self, *parts: object) -> Any: ...

    async def aclose(self) -> None: ...


def encode_envelope_fields(envelope: EventEnvelope) -> list[str]:
    """Serialize an envelope into the flat ``XADD`` field list used on the stream."""
    return [ENVELOPE_FIELD, envelope.model_dump_json()]


def decode_envelope_fields(fields: list[str]) -> EventEnvelope:
    payload = {fields[i]: fields[i + 1] for i in range(0, len(fields), 2)}
    raw = json.loads(payload[ENVELOPE_FIELD])
    return EventEnvelope.model_validate(raw)


async def publish_envelope(
    client: StreamClient,
    stream: str,
    envelope: EventEnvelope,
    *,
    maxlen: int,
) -> str:
    """Publish an envelope to the shared ingest stream with approximate MAXLEN.

    Used by the HTTP backfill path and tests; producers do the same XADD.
    """
    entry_id = await client.execute(
        "XADD",
        stream,
        "MAXLEN",
        "~",
        str(maxlen),
        "*",
        ENVELOPE_FIELD,
        envelope.model_dump_json(),
    )
    return str(entry_id)


class LagSignalSink(Protocol):
    async def emit_consumer_lag(self, stream: str, group: str, lag: int) -> None: ...


class LoggingLagSink:
    """Default lag sink: logs a warning (observability capability hook point)."""

    async def emit_consumer_lag(self, stream: str, group: str, lag: int) -> None:
        logger.warning(
            "history ingest consumer lag exceeded threshold: stream=%s group=%s lag=%s",
            stream,
            group,
            lag,
        )


class StreamIngester:
    """Consumer-group ingester reading the shared ``history:ingest`` stream.

    Multiple replicas share one consumer group; each claims its own consumer
    name so pending entries are tracked per replica. Commits are idempotent, so
    at-least-once delivery and concurrent replicas converge on a single gap-free
    per-game seq series.
    """

    def __init__(
        self,
        *,
        settings: Settings,
        repository: Repository,
        client: RespConnection,
        snapshots: SnapshotService | None = None,
        lag_sink: LagSignalSink | None = None,
    ):
        self._settings = settings
        self._repository = repository
        self._client = client
        self._snapshots = snapshots
        self._lag_sink = lag_sink or LoggingLagSink()
        self._stream = settings.history_ingest_stream
        self._group = settings.history_ingest_consumer_group
        self._consumer = settings.consumer_name
        self._running = False
        self._stopped = asyncio.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    async def ensure_group(self) -> None:
        """Create the consumer group (idempotent); tolerate BUSYGROUP."""
        try:
            await self._client.execute(
                "XGROUP",
                "CREATE",
                self._stream,
                self._group,
                "$",
                "MKSTREAM",
            )
        except Exception as exc:  # noqa: BLE001
            if "BUSYGROUP" not in str(exc):
                raise

    async def process_batch(self) -> int:
        """Read and commit a batch of new entries; returns the count processed.

        Reclaims stale pending entries first so a crashed replica's or a
        previously-failed entry's work is recovered before new entries are read.
        """
        # One span per batch, not per event: the ingester polls continuously, so
        # a span per entry would swamp the collector with idle no-op spans. Only
        # stream/group identity and counts go on it — never an event payload.
        with tracer.start_as_current_span(
            "history.ingest_batch",
            attributes={
                "history.stream": self._stream,
                "history.consumer_group": self._group,
            },
        ) as span:
            # Reclaiming is a best-effort recovery pass, so a failure here must not
            # cost us the batch. It used to: one failed XAUTOCLAIM aborted
            # process_batch, so nothing was ever read and the loop retried in a hot
            # cycle (DRA-35). Stale entries stay pending and the next poll retries
            # them, which is exactly what XAUTOCLAIM's idle window is for.
            try:
                await self.reclaim_pending()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Reclaiming pending entries failed (%s: %s); "
                    "continuing with this batch",
                    type(exc).__name__,
                    exc,
                )
                span.set_attribute("history.reclaim_failed", True)
            response = await self._client.execute(
                "XREADGROUP",
                "GROUP",
                self._group,
                self._consumer,
                "COUNT",
                str(self._settings.ingester_batch_size),
                "BLOCK",
                str(self._settings.ingester_poll_block_ms),
                "STREAMS",
                self._stream,
                ">",
            )
            if not response:
                span.set_attribute("history.events_processed", 0)
                await self._check_lag()
                return 0
            _, entries = response[0]
            processed = 0
            for entry_id, fields in entries:
                await self._handle_entry(entry_id, fields)
                processed += 1
            span.set_attribute("history.events_processed", processed)
            await self._check_lag()
            return processed

    async def reclaim_pending(self) -> int:
        """Reclaim and re-process stale pending entries; returns the count claimed.

        A pending entry lingers when its consumer crashed (the consumer name is
        ``hostname:pid``, so the PID changes on restart and its PEL is orphaned)
        or when a transient commit failure left it un-acked. ``XAUTOCLAIM`` moves
        entries idle longer than ``history_ingest_claim_min_idle_ms`` onto this
        consumer, and they are re-run through the idempotent commit path. Because
        commits dedupe on ``(game_id, idempotency_key)``, re-processing a
        duplicate is safe and never consumes a ``seq``.
        """
        min_idle = str(self._settings.history_ingest_claim_min_idle_ms)
        count = str(self._settings.ingester_batch_size)
        reclaimed = 0
        cursor = "0-0"
        while True:
            try:
                response = await self._client.execute(
                    "XAUTOCLAIM",
                    self._stream,
                    self._group,
                    self._consumer,
                    min_idle,
                    cursor,
                    "COUNT",
                    count,
                )
            except RespError as exc:
                if _is_unknown_command(exc):
                    return await self._reclaim_pending_fallback(min_idle, count)
                raise
            if not response:
                break
            cursor = response[0]
            entries = response[1] if len(response) > 1 else []
            reclaimed += await self._process_claimed(entries or [])
            # A returned cursor of "0-0" (or "0") marks the end of the scan.
            if cursor in ("0-0", "0", None):
                break
        return reclaimed

    async def _reclaim_pending_fallback(self, min_idle: str, count: str) -> int:
        """Reclaim via XPENDING + XCLAIM when the server lacks XAUTOCLAIM."""
        summary = await self._client.execute(
            "XPENDING",
            self._stream,
            self._group,
            "IDLE",
            min_idle,
            "-",
            "+",
            count,
        )
        if not summary:
            return 0
        ids = [row[0] for row in summary]
        claimed = await self._client.execute(
            "XCLAIM",
            self._stream,
            self._group,
            self._consumer,
            min_idle,
            *ids,
        )
        return await self._process_claimed(claimed or [])

    async def _process_claimed(self, entries: list) -> int:
        processed = 0
        for entry_id, fields in entries:
            if fields is None:
                # The entry was trimmed/deleted from the stream; the claim has
                # already dropped it from the pending list, so nothing to do.
                continue
            await self._handle_entry(entry_id, fields)
            processed += 1
        return processed

    async def _handle_entry(
        self, entry_id: str, fields: list[str]
    ) -> CommitResult | None:
        try:
            envelope = decode_envelope_fields(fields)
        except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as exc:
            # A malformed entry can never be committed; ack it so it does not
            # wedge the pending list, and surface the problem in logs.
            logger.error("Dropping malformed ingest entry %s: %s", entry_id, exc)
            await self._ack(entry_id)
            return None
        try:
            result = await self._repository.commit_event(envelope)
        except Exception:  # noqa: BLE001
            # A transient commit failure (deadlock/connection blip) must not
            # abort the rest of the batch or lose the entry. Leave it UN-acked so
            # it stays in the pending list and is reclaimed on a later cycle via
            # reclaim_pending(); the idempotent commit makes the retry safe.
            logger.exception("Deferring ingest entry %s after commit failure", entry_id)
            return None
        # Evaluate snapshot cadence after a real commit. This is the production
        # ingest path (events arrive via the Valkey stream), so without this the
        # cadence policy would never fire and restore would have no base
        # snapshot. Best-effort: a snapshot failure must never block acking an
        # already-committed event.
        if self._snapshots is not None and result.inserted:
            await self._snapshots.maybe_snapshot_best_effort(
                result.event.game_id, result.event.seq, result.event.platform
            )
        await self._ack(entry_id)
        return result

    async def _ack(self, entry_id: str) -> None:
        await self._client.execute("XACK", self._stream, self._group, entry_id)

    async def _check_lag(self) -> None:
        threshold = self._settings.history_consumer_lag_alert_threshold
        if threshold <= 0:
            return
        lag = await self.consumer_lag()
        if lag is not None and lag > threshold:
            await self._lag_sink.emit_consumer_lag(self._stream, self._group, lag)

    async def consumer_lag(self) -> int | None:
        """Return the consumer-group lag (undelivered entries), if known."""
        try:
            info = await self._client.execute("XINFO", "GROUPS", self._stream)
        except Exception:  # noqa: BLE001
            return None
        if not info:
            return None
        for group in info:
            attrs = {group[i]: group[i + 1] for i in range(0, len(group), 2)}
            if attrs.get("name") == self._group:
                lag = attrs.get("lag")
                if lag is None:
                    return None
                try:
                    return int(lag)
                except TypeError, ValueError:
                    return None
        return None

    async def run_forever(self) -> None:
        self._running = True
        self._stopped.clear()
        await self.ensure_group()
        logger.info(
            "Stream ingester started: stream=%s group=%s consumer=%s",
            self._stream,
            self._group,
            self._consumer,
        )
        backoff = INGEST_RETRY_MIN_SECONDS
        failures = 0
        try:
            while self._running:
                try:
                    await self.process_batch()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    failures += 1
                    # One traceback per outage, not one per retry. This used to log a
                    # full stack every 500ms for as long as Valkey was unhappy, which
                    # buried every other line in the log (DRA-35). The first failure
                    # carries the diagnosis; the rest are counted, and the delay grows
                    # so a sustained outage costs a handful of lines, not thousands.
                    if failures == 1:
                        logger.exception(
                            "Ingest batch failed; retrying in %.1fs", backoff
                        )
                    else:
                        logger.warning(
                            "Ingest batch still failing (%d consecutive); "
                            "retrying in %.1fs",
                            failures,
                            backoff,
                        )
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, INGEST_RETRY_MAX_SECONDS)
                else:
                    if failures:
                        logger.info(
                            "Ingest batch recovered after %d consecutive failure(s)",
                            failures,
                        )
                    failures = 0
                    backoff = INGEST_RETRY_MIN_SECONDS
        finally:
            self._running = False
            self._stopped.set()

    async def stop(self) -> None:
        self._running = False
