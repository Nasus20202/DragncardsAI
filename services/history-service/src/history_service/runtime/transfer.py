from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from history_service.runtime.bundle_codec import (
    BlobTable,
    BlobTableError,
    BlobTableTooLargeError,
    BlobWriter,
)
from history_service.schemas.transfer import (
    AGENT_MOVE_EVENT_TYPE,
    BUNDLE_FORMAT,
    BUNDLE_FORMAT_VERSION,
    BUNDLE_SUPPORTED_FORMAT_VERSIONS,
    CONVERSATION_CONTEXT_FIELD,
    BundleBlob,
    BundleEvent,
    BundleFooter,
    BundleHeader,
    BundleMode,
    BundleSnapshot,
    omitted_payload_fields_for,
)
from history_service.schemas.envelope import PLATFORM_DRAGNCARDS, Platform
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


def bundle_filename(game_id: str, mode: BundleMode = "full") -> str:
    """A download filename for a game's bundle.

    ``game_id`` is already constrained to ``[A-Za-z0-9_-]{1,64}`` at the route
    boundary, and ``mode`` is one of two literals, so neither can inject quotes
    or newlines into the ``Content-Disposition`` header this is interpolated
    into. The mode is in the name so two exports of one game do not overwrite
    each other in a downloads folder.
    """
    return f"dragncards-history-{game_id}-{mode}.ndjson"


def _payload_for_mode(
    event_type: str, payload: dict[str, Any], mode: BundleMode
) -> dict[str, Any]:
    """The payload a mode exports.

    ``minimal`` removes the key rather than emptying it. That distinction is the
    whole point: an absent ``conversation_context`` says "this recording carries
    no prompts", while ``[]`` would say "the prompts were empty", and the restore
    path cannot tell those apart — it returns ``[]`` for both and reports the
    agent context restored either way.
    """
    if mode != "minimal" or event_type != AGENT_MOVE_EVENT_TYPE:
        return payload
    if CONVERSATION_CONTEXT_FIELD not in payload:
        return payload
    return {
        key: value
        for key, value in payload.items()
        if key != CONVERSATION_CONTEXT_FIELD
    }


async def resolve_plugin_name(
    repo: Repository, game_id: str, platform: Platform = PLATFORM_DRAGNCARDS
) -> str | None:
    """The plugin slug recorded for a game, if any.

    Recorded on both snapshot documents and every game-state event payload;
    mirrors the preference order ``RestoreService._resolve_plugin_name`` uses.
    Best-effort — a game with neither simply exports ``null``.
    """
    snapshots = await repo.list_snapshots(game_id, platform=platform, limit=1)
    if snapshots:
        candidate = snapshots[0].snapshot.get("plugin_name")
        if isinstance(candidate, str) and candidate:
            return candidate
    earliest = await repo.get_earliest_state_event(game_id, platform)
    if earliest is not None:
        candidate = earliest.payload.get("plugin_name")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


async def iter_export_lines(
    repo: Repository,
    game_id: str,
    *,
    mode: BundleMode = "full",
    platform: Platform = PLATFORM_DRAGNCARDS,
) -> AsyncIterator[str]:
    """Stream a game's whole recorded history as NDJSON lines.

    Never materializes the bundle: events and snapshots are read a page at a
    time and yielded as they are read, so a game whose every event embeds a full
    board state does not have to fit in memory. A record's repeated
    substructures are emitted as ``blob`` records immediately before the record
    that first references them, which keeps the write a single forward pass.

    An unknown game yields a header/footer pair with zero counts rather than an
    error, matching the read endpoints' "unknown games return empty results"
    convention. Import rejects such a bundle, so the emptiness is still caught
    loudly at the point where it would matter.
    """
    event_count = await repo.count_events_since_seq(game_id, 0, platform)
    snapshot_count = await repo.count_snapshots(game_id, platform)
    plugin_name = await resolve_plugin_name(repo, game_id, platform)

    yield _dump_line(
        BundleHeader(
            kind="header",
            format=BUNDLE_FORMAT,
            format_version=BUNDLE_FORMAT_VERSION,
            game_id=game_id,
            platform=platform,
            plugin_name=plugin_name,
            exported_at=datetime.now(timezone.utc),
            event_count=event_count,
            snapshot_count=snapshot_count,
            mode=mode,
            omitted_payload_fields=omitted_payload_fields_for(mode),
        ).model_dump()
    )

    # One writer for the whole bundle: the plugin's static definitions are
    # byte-identical on every state, so they are worth carrying once per game
    # rather than once per record.
    writer = BlobWriter()

    after_seq = 0
    while True:
        events = await repo.list_events(
            game_id, platform=platform, after_seq=after_seq, limit=EXPORT_PAGE_SIZE
        )
        if not events:
            break
        for event in events:
            record = event.model_dump()
            # The target game is chosen at import time; a per-line copy of the
            # source id would only be a second, conflicting source of truth.
            record.pop("game_id", None)
            # Version 2 declares platform once in the header. Repeating it on
            # every event would create a second source of truth.
            record.pop("platform", None)
            record["kind"] = "event"
            payload = _payload_for_mode(event.event_type, record["payload"], mode)
            record["payload"], blobs = writer.encode(
                payload, f"event[{event.seq}].payload"
            )
            for blob in blobs:
                yield _dump_line(blob)
            yield _dump_line(record)
        after_seq = events[-1].seq
        if len(events) < EXPORT_PAGE_SIZE:
            break

    after_snapshot_seq = 0
    while True:
        snapshots = await repo.list_snapshots(
            game_id,
            platform=platform,
            after_seq=after_snapshot_seq,
            limit=EXPORT_PAGE_SIZE,
        )
        if not snapshots:
            break
        for snapshot in snapshots:
            record = snapshot.model_dump()
            record.pop("game_id", None)
            # The header is the sole platform field in a version-2 export.
            record.pop("platform", None)
            record["kind"] = "snapshot"
            record["snapshot"], blobs = writer.encode(
                record["snapshot"],
                f"snapshot[{snapshot.snapshot_at_seq}].snapshot",
            )
            for blob in blobs:
                yield _dump_line(blob)
            yield _dump_line(record)
        after_snapshot_seq = snapshots[-1].snapshot_at_seq
        if len(snapshots) < EXPORT_PAGE_SIZE:
            break

    yield _dump_line(
        BundleFooter(
            kind="footer",
            event_count=event_count,
            snapshot_count=snapshot_count,
            blob_count=writer.blob_count,
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
    if header.format_version not in BUNDLE_SUPPORTED_FORMAT_VERSIONS:
        supported = ", ".join(str(v) for v in BUNDLE_SUPPORTED_FORMAT_VERSIONS)
        raise BundleError(
            f"line {line_number}: unsupported bundle format_version "
            f"{header.format_version} (this service reads versions {supported})"
        )
    if header.mode == "full" and header.omitted_payload_fields:
        raise BundleError(
            f"line {line_number}: header declares mode 'full' but also names "
            f"omitted payload fields {header.omitted_payload_fields}; the two "
            "statements contradict each other"
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
        self._max_bytes = max_bytes
        self.header: BundleHeader | None = None
        self.event_count = 0
        self.snapshot_count = 0
        self.blob_count = 0
        self.first_seq: int | None = None
        self.last_seq: int | None = None
        self.source_id_references = 0
        self._last_snapshot_seq: int | None = None
        self._blobs: BlobTable | None = None
        self._blobs_allowed = False

    async def read_header(self) -> BundleHeader:
        """Consume and validate the first line.

        Read separately from the body because the header names the bundle's own
        ``game_id``, which is the default import target — the caller has to know
        where the history is going before the writing transaction is opened.
        ``records()`` resumes the same line stream afterwards.
        """
        async for line_number, line in self._lines:
            self.header = parse_header(line_number, line)
            self._blobs = BlobTable(
                max_expanded_bytes=self._max_bytes,
                source_game_id=self.header.game_id,
            )
            # Version 1 did not define the record kind, so a blob inside one is
            # rejected rather than silently accepted by a newer reader. The table
            # itself is still built: it is also what counts the payloads that
            # still name the source game, which a version 1 bundle has too.
            self._blobs_allowed = self.header.format_version >= 2
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
            elif kind == "blob":
                self._accept_blob(line_number, record)
            elif kind == "footer":
                self._accept_footer(line_number, record)
                saw_footer = True
            else:
                raise BundleError(
                    f"line {line_number}: unknown record kind {kind!r} "
                    "(expected 'blob', 'event', 'snapshot', or 'footer')"
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

    def _accept_blob(self, line_number: int, record: dict[str, Any]) -> None:
        if self._blobs is None or not self._blobs_allowed:
            raise BundleError(
                f"line {line_number}: a 'blob' record is not valid in a version "
                "1 bundle, which did not define that record kind"
            )
        blob: BundleBlob = _validate(line_number, BundleBlob, record)
        try:
            self._blobs.add(line_number, blob.id, blob.value)
        except BlobTableError as exc:
            raise BundleError(str(exc)) from exc
        except BlobTableTooLargeError as exc:
            raise BundleTooLargeError(str(exc)) from exc
        self.blob_count += 1

    def _resolve(self, line_number: int, what: str, value: Any) -> tuple[Any, bool]:
        """Expand a record's references, and say whether it names the source.

        Returns the value unchanged for a version 1 bundle, which has no blob
        table. The expansion is priced before it is built, so a bundle that is
        small on disk but describes a huge expansion is refused rather than
        materialized.
        """
        if self._blobs is None:
            return value, False
        try:
            size = self._blobs.expanded_size(line_number, value)
            if size > self._max_bytes:
                raise BundleTooLargeError(
                    f"line {line_number}: {what} expands to about {size} bytes, "
                    f"over the {self._max_bytes}-byte ceiling"
                )
            mentions = self._blobs.mentions_source(value)
            return self._blobs.resolve(line_number, value), mentions
        except BlobTableError as exc:
            raise BundleError(str(exc)) from exc
        except BlobTableTooLargeError as exc:
            raise BundleTooLargeError(str(exc)) from exc

    def _accept_event(self, line_number: int, record: dict[str, Any]) -> BundleEvent:
        event: BundleEvent = _validate(line_number, BundleEvent, record)
        payload, mentions = self._resolve(
            line_number, f"event seq {event.seq}", event.payload
        )
        if not isinstance(payload, dict):
            # ``model_copy`` does not re-validate, so a reference that resolves
            # to an array has to be caught here rather than reaching storage.
            raise BundleError(
                f"line {line_number}: event payload resolves to a "
                f"{type(payload).__name__}, expected an object"
            )
        event = event.model_copy(update={"payload": payload})
        if mentions:
            self.source_id_references += 1
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
        document, _ = self._resolve(
            line_number,
            f"snapshot at seq {snapshot.snapshot_at_seq}",
            snapshot.snapshot,
        )
        if not isinstance(document, dict):
            raise BundleError(
                f"line {line_number}: snapshot resolves to a "
                f"{type(document).__name__}, expected an object"
            )
        snapshot = snapshot.model_copy(update={"snapshot": document})
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
        if footer.blob_count != self.blob_count:
            raise BundleError(
                f"line {line_number}: footer declares {footer.blob_count} "
                f"blobs but {self.blob_count} were read"
            )
