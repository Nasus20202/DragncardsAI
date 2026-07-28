from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from history_service.schemas.transfer import (
    BUNDLE_FORMAT,
    BUNDLE_FORMAT_VERSION,
    BundleEvent,
    BundleFooter,
    BundleHeader,
    BundleSnapshot,
)
from history_service.storage.repository import Repository

# How many rows one database read pulls while streaming an export. Bounds the
# resident slice of a game whose every event embeds a full board state.
EXPORT_PAGE_SIZE = 200


class BundleError(Exception):
    """A bundle is not acceptable. The message is safe to show a caller."""


class BundleTooLargeError(BundleError):
    """The body exceeded the configured import ceiling."""


def _dump_line(record: dict[str, Any]) -> str:
    # ``sort_keys`` is what makes two exports of the same game diff cleanly:
    # key order never depends on insertion order or dict iteration.
    return json.dumps(record, sort_keys=True, default=_json_default) + "\n"


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def bundle_filename(game_id: str) -> str:
    """A download filename for a game's bundle.

    ``game_id`` is already constrained to ``[A-Za-z0-9_-]{1,64}`` at the route
    boundary, so it cannot inject quotes or newlines into the
    ``Content-Disposition`` header this is interpolated into.
    """
    return f"dragncards-history-{game_id}.ndjson"


async def resolve_plugin_name(repo: Repository, game_id: str) -> str | None:
    """The plugin slug recorded for a game, if any.

    Recorded on both snapshot documents and every game-state event payload;
    mirrors the preference order ``RestoreService._resolve_plugin_name`` uses.
    Best-effort — a game with neither simply exports ``null``.
    """
    snapshots = await repo.list_snapshots(game_id, limit=1)
    if snapshots:
        candidate = snapshots[0].snapshot.get("plugin_name")
        if isinstance(candidate, str) and candidate:
            return candidate
    earliest = await repo.get_earliest_state_event(game_id)
    if earliest is not None:
        candidate = earliest.payload.get("plugin_name")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


async def iter_export_lines(repo: Repository, game_id: str) -> AsyncIterator[str]:
    """Stream a game's whole recorded history as NDJSON lines.

    Never materializes the bundle: events and snapshots are read a page at a
    time and yielded as they are read, so a game whose every event embeds a full
    board state does not have to fit in memory.

    An unknown game yields a header/footer pair with zero counts rather than an
    error, matching the read endpoints' "unknown games return empty results"
    convention. Import rejects such a bundle, so the emptiness is still caught
    loudly at the point where it would matter.
    """
    event_count = await repo.count_events_since_seq(game_id, 0)
    snapshot_count = await repo.count_snapshots(game_id)
    plugin_name = await resolve_plugin_name(repo, game_id)

    yield _dump_line(
        BundleHeader(
            kind="header",
            format=BUNDLE_FORMAT,
            format_version=BUNDLE_FORMAT_VERSION,
            game_id=game_id,
            plugin_name=plugin_name,
            exported_at=datetime.now(timezone.utc),
            event_count=event_count,
            snapshot_count=snapshot_count,
        ).model_dump()
    )

    after_seq = 0
    while True:
        events = await repo.list_events(
            game_id, after_seq=after_seq, limit=EXPORT_PAGE_SIZE
        )
        if not events:
            break
        for event in events:
            record = event.model_dump()
            # The target game is chosen at import time; a per-line copy of the
            # source id would only be a second, conflicting source of truth.
            record.pop("game_id", None)
            record["kind"] = "event"
            yield _dump_line(record)
        after_seq = events[-1].seq
        if len(events) < EXPORT_PAGE_SIZE:
            break

    after_snapshot_seq = 0
    while True:
        snapshots = await repo.list_snapshots(
            game_id, after_seq=after_snapshot_seq, limit=EXPORT_PAGE_SIZE
        )
        if not snapshots:
            break
        for snapshot in snapshots:
            record = snapshot.model_dump()
            record.pop("game_id", None)
            record["kind"] = "snapshot"
            yield _dump_line(record)
        after_snapshot_seq = snapshots[-1].snapshot_at_seq
        if len(snapshots) < EXPORT_PAGE_SIZE:
            break

    yield _dump_line(
        BundleFooter(
            kind="footer",
            event_count=event_count,
            snapshot_count=snapshot_count,
        ).model_dump()
    )


async def iter_bundle_lines(
    chunks: AsyncIterator[bytes], *, max_bytes: int
) -> AsyncIterator[tuple[int, bytes]]:
    """Split a streamed body into ``(line_number, line)`` pairs.

    Enforces ``max_bytes`` against the running total as chunks arrive, so an
    oversized upload is refused while it is still being read rather than after
    it has been buffered. Blank lines are skipped so a trailing newline (or a
    file a person edited) is not an error.
    """
    buffer = bytearray()
    total = 0
    line_number = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > max_bytes:
            raise BundleTooLargeError("Request body too large")
        buffer.extend(chunk)
        while True:
            newline = buffer.find(b"\n")
            if newline < 0:
                break
            line = bytes(buffer[:newline])
            del buffer[: newline + 1]
            line_number += 1
            if line.strip():
                yield line_number, line
    if buffer.strip():
        line_number += 1
        yield line_number, bytes(buffer)


def _load_record(line_number: int, line: bytes) -> dict[str, Any]:
    try:
        record = json.loads(line)
    except (UnicodeDecodeError, ValueError) as exc:
        raise BundleError(f"line {line_number}: not valid JSON ({exc})") from exc
    if not isinstance(record, dict):
        raise BundleError(
            f"line {line_number}: expected a JSON object, got "
            f"{type(record).__name__}"
        )
    return record


def _validate(line_number: int, model: type, record: dict[str, Any]) -> Any:
    try:
        return model.model_validate(record)
    except ValidationError as exc:
        raise BundleError(
            f"line {line_number}: invalid {record.get('kind')} record: "
            f"{_first_error(exc)}"
        ) from exc


def _first_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:  # pragma: no cover - pydantic always reports at least one
        return str(exc)
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ())) or "(root)"
    return f"{location}: {first.get('msg')}"


def parse_header(line_number: int, line: bytes) -> BundleHeader:
    """Validate the first line and the format it declares."""
    record = _load_record(line_number, line)
    if record.get("kind") != "header":
        raise BundleError(
            f"line {line_number}: a bundle must start with a 'header' record, "
            f"got {record.get('kind')!r}"
        )
    header: BundleHeader = _validate(line_number, BundleHeader, record)
    if header.format != BUNDLE_FORMAT:
        raise BundleError(
            f"line {line_number}: unsupported bundle format {header.format!r} "
            f"(expected {BUNDLE_FORMAT!r})"
        )
    if header.format_version != BUNDLE_FORMAT_VERSION:
        raise BundleError(
            f"line {line_number}: unsupported bundle format_version "
            f"{header.format_version} (this service reads version "
            f"{BUNDLE_FORMAT_VERSION})"
        )
    return header


class BundleReader:
    """Validates a bundle record by record while it is being read.

    Structural invariants are checked as the stream advances — the header comes
    first, event ``seq`` values are strictly ascending and gap-free from 1,
    snapshots follow the events in ascending order and none points past the last
    event, and the footer's counts match what was actually read. Nothing is
    buffered beyond the record in hand and the running counters, and the caller
    consumes the records inside a single database transaction, so a bundle that
    fails anywhere imports nothing.
    """

    def __init__(self, chunks: AsyncIterator[bytes], *, max_bytes: int):
        self._lines = iter_bundle_lines(chunks, max_bytes=max_bytes)
        self.header: BundleHeader | None = None
        self.event_count = 0
        self.snapshot_count = 0
        self.first_seq: int | None = None
        self.last_seq: int | None = None
        self._last_snapshot_seq: int | None = None

    async def read_header(self) -> BundleHeader:
        """Consume and validate the first line.

        Read separately from the body because the header names the bundle's own
        ``game_id``, which is the default import target — the caller has to know
        where the history is going before the writing transaction is opened.
        ``records()`` resumes the same line stream afterwards.
        """
        async for line_number, line in self._lines:
            self.header = parse_header(line_number, line)
            return self.header
        raise BundleError("bundle is empty: no 'header' record was read")

    async def records(self) -> AsyncIterator[BundleEvent | BundleSnapshot]:
        if self.header is None:  # pragma: no cover - guarded by the router
            raise BundleError("read_header() must be called before records()")
        saw_footer = False
        async for line_number, line in self._lines:
            if saw_footer:
                raise BundleError(
                    f"line {line_number}: content after the 'footer' record "
                    "(is this two bundles concatenated?)"
                )
            record = _load_record(line_number, line)
            kind = record.get("kind")
            if kind == "event":
                yield self._accept_event(line_number, record)
            elif kind == "snapshot":
                yield self._accept_snapshot(line_number, record)
            elif kind == "footer":
                self._accept_footer(line_number, record)
                saw_footer = True
            else:
                raise BundleError(
                    f"line {line_number}: unknown record kind {kind!r} "
                    "(expected 'event', 'snapshot', or 'footer')"
                )

        if not saw_footer:
            raise BundleError(
                "bundle is truncated: no 'footer' record was read "
                f"(got {self.event_count} events and "
                f"{self.snapshot_count} snapshots)"
            )
        if self.event_count == 0:
            raise BundleError(
                "bundle contains no events, so there is nothing to import"
            )

    def _accept_event(self, line_number: int, record: dict[str, Any]) -> BundleEvent:
        event: BundleEvent = _validate(line_number, BundleEvent, record)
        if self.snapshot_count:
            raise BundleError(
                f"line {line_number}: event seq {event.seq} appears after a "
                "snapshot record; all events must precede all snapshots"
            )
        expected = 1 if self.last_seq is None else self.last_seq + 1
        if event.seq != expected:
            raise BundleError(
                f"line {line_number}: event seq must be gap-free and ascending "
                f"from 1; expected {expected}, got {event.seq}"
            )
        if self.first_seq is None:
            self.first_seq = event.seq
        self.last_seq = event.seq
        self.event_count += 1
        return event

    def _accept_snapshot(
        self, line_number: int, record: dict[str, Any]
    ) -> BundleSnapshot:
        snapshot: BundleSnapshot = _validate(line_number, BundleSnapshot, record)
        if self.last_seq is None or snapshot.snapshot_at_seq > self.last_seq:
            raise BundleError(
                f"line {line_number}: snapshot_at_seq "
                f"{snapshot.snapshot_at_seq} is beyond the last event seq "
                f"{self.last_seq if self.last_seq is not None else 0}"
            )
        if (
            self._last_snapshot_seq is not None
            and snapshot.snapshot_at_seq <= self._last_snapshot_seq
        ):
            # Caught here rather than by the store's unique constraint so the
            # message names the line and says what is actually wrong.
            raise BundleError(
                f"line {line_number}: snapshot_at_seq must be ascending; "
                f"{snapshot.snapshot_at_seq} follows {self._last_snapshot_seq}"
            )
        self._last_snapshot_seq = snapshot.snapshot_at_seq
        self.snapshot_count += 1
        return snapshot

    def _accept_footer(self, line_number: int, record: dict[str, Any]) -> None:
        footer: BundleFooter = _validate(line_number, BundleFooter, record)
        if footer.event_count != self.event_count:
            raise BundleError(
                f"line {line_number}: footer declares {footer.event_count} "
                f"events but {self.event_count} were read"
            )
        if footer.snapshot_count != self.snapshot_count:
            raise BundleError(
                f"line {line_number}: footer declares {footer.snapshot_count} "
                f"snapshots but {self.snapshot_count} were read"
            )
