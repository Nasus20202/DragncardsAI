"""Blob extraction and resolution for bundle format version 2.

A recorded game is overwhelmingly repetition: every ``game_state`` event
re-ships DragnCards' whole delta log, every ``agent_move`` re-ships the
conversation that preceded it, and the plugin's DragnLang functions, automation
lists, rules and layout are byte-identical on every state. Version 2 therefore
carries any repeated value **once**, as a ``blob`` record, and references it
from every place it occurs.

The extraction rule is deliberately generic: any object or array whose
serialization reaches :data:`DEDUP_THRESHOLD_BYTES` is pulled out. Nothing here
knows a field name, so the format does not have to be revised when a recorded
DragnCards state gains a field.

Two properties make the format streamable in both directions:

* references are **backward only** — a reference names a blob defined on an
  earlier line, so a bundle is written and read in one forward pass and a
  reference cycle cannot be expressed;
* blobs are emitted in post-order, so a blob's own references are always
  already defined when it is read.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Extraction threshold, in bytes of serialized (already-referenced) form.
#
# 128 bytes is smaller still but pulls four-line fragments onto their own lines,
# so a reader chases a reference for something they could have read in place;
# 512 leaves DragnCards' per-card entries inline and the file more than doubles.
# 256 is roughly "big enough that you would have scrolled past it anyway".
DEDUP_THRESHOLD_BYTES = 256

# How deep a bundle's values may nest. Reading a bundle recurses over structure
# an untrusted file chose, and Python's stack overflows at around a thousand
# frames — a `RecursionError` is a 500 where a bounded refusal is a 400. A real
# recorded DragnCards state nests about ten levels, so 200 is far past anything
# the producers emit and far short of the interpreter's limit.
MAX_NESTING_DEPTH = 200

# The reference marker, and the escape for a payload that genuinely contains it.
REF_KEY = "$ref"
LITERAL_KEY = "$literal"
_MARKER_KEYS = (REF_KEY, LITERAL_KEY)


def _is_marker_object(value: Any) -> bool:
    """True for an object whose *only* key is ``$ref`` or ``$literal``."""
    return (
        isinstance(value, dict)
        and len(value) == 1
        and next(iter(value)) in _MARKER_KEYS
    )


def canonical(value: Any) -> str:
    """The serialization used for both deduplication keys and size decisions."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class BlobWriter:
    """Extracts repeated substructures out of record payloads.

    One writer serves a whole export: the deduplication table spans every
    record, which is what lets the plugin's static definitions be carried once
    for the whole game rather than once per event.
    """

    def __init__(self, *, threshold: int = DEDUP_THRESHOLD_BYTES) -> None:
        self._threshold = threshold
        # sha256 of the canonical serialization of the *encoded* value -> blob
        # id. Keying on the encoded form is equivalent to keying on the original
        # (encoding is deterministic) and avoids serializing the expanded value
        # at all.
        self._ids: dict[bytes, str] = {}
        self.blob_count = 0

    def encode(
        self, value: dict[str, Any], path: str
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Encode one record's payload.

        Returns the value with extracted substructures replaced by references,
        together with the ``blob`` records that must be written *before* the
        record that references them. ``path`` is the dotted location of the
        payload within the bundle (``event[42].payload``); it is recorded on
        each new blob as ``first_seen`` so a reader can find out what a
        reference stands for by grepping rather than by decoding the file.

        The payload itself is never extracted, only its members. Pulling it out
        whole would replace the record's own line with ``{"$ref": "b7"}``,
        which costs a blob wrapper and a reference for no saving — measured on
        a real 124-event game it is 5 KB *larger* — and hides what the record
        is: with the root left in place an ``event`` line still shows its
        action, its arguments and its status, and references only the board
        state it shares with its neighbours.
        """
        blobs: list[dict[str, Any]] = []
        if _is_marker_object(value):
            # A payload whose only key is a marker would be read back as a
            # reference, so it is escaped even at the root, where escaping is
            # correctness rather than compression.
            key = next(iter(value))
            return {
                LITERAL_KEY: {key: self._encode(value[key], f"{path}.{key}", blobs)}
            }, blobs
        encoded = {
            key: self._encode(value[key], f"{path}.{key}", blobs)
            for key in sorted(value)
        }
        return encoded, blobs

    def _encode(self, value: Any, path: str, blobs: list[dict[str, Any]]) -> Any:
        if isinstance(value, dict):
            if _is_marker_object(value):
                # The payload's own object would be read back as a reference or
                # an escape, so wrap it. This nests: the wrapper is itself a
                # marker object, and unwrapping is applied once per wrapper.
                key = next(iter(value))
                encoded: Any = {
                    LITERAL_KEY: {key: self._encode(value[key], f"{path}.{key}", blobs)}
                }
            else:
                # Walked in sorted order, like every bundle line is written.
                # Blob ids are assigned in first-encounter order, so walking a
                # dict in *insertion* order would make them depend on how the
                # payload happened to be built — and a re-export of an imported
                # game, whose keys came back sorted from the file, would then
                # renumber every blob.
                encoded = {
                    key: self._encode(value[key], f"{path}.{key}", blobs)
                    for key in sorted(value)
                }
        elif isinstance(value, list):
            encoded = [
                self._encode(item, f"{path}[{index}]", blobs)
                for index, item in enumerate(value)
            ]
        else:
            return value
        return self._maybe_extract(encoded, path, blobs)

    def _maybe_extract(
        self, encoded: Any, path: str, blobs: list[dict[str, Any]]
    ) -> Any:
        serialized = canonical(encoded)
        if len(serialized) < self._threshold:
            return encoded
        # Keyed by digest rather than by the text itself. Keying by text would
        # make the table hold a second copy of every distinct value in the game,
        # which is the one thing a streaming export is supposed to avoid; a
        # 32-byte digest makes the table's size a function of how many distinct
        # values there are rather than how large they are.
        digest = hashlib.sha256(serialized.encode("utf-8")).digest()
        existing = self._ids.get(digest)
        if existing is not None:
            return {REF_KEY: existing}
        self.blob_count += 1
        blob_id = f"b{self.blob_count}"
        self._ids[digest] = blob_id
        # Post-order: children were appended first, so a blob's own references
        # are always defined on an earlier line than the blob itself.
        blobs.append(
            {
                "kind": "blob",
                "id": blob_id,
                "first_seen": path,
                "value": encoded,
            }
        )
        return {REF_KEY: blob_id}


class BlobTableError(Exception):
    """A bundle's blob references do not resolve. Message names the fault."""


class BlobTableTooLargeError(Exception):
    """What a bundle's references describe exceeds the import ceiling."""


class BlobTable:
    """Resolves ``$ref`` markers against the blobs already read.

    Values are stored **resolved**, so a blob that references earlier blobs is
    expanded once rather than once per reference. Python aliasing means the
    shared substructures are shared objects, not copies, so the table's real
    memory cost is the bundle's distinct content — but the *serialized* size a
    reference describes can still grow exponentially (``b2 = [b1, b1]``,
    ``b3 = [b2, b2]``, ...), and that is what a database write would have to
    materialize. Each blob's expanded size is therefore accounted for as it is
    read, and a bundle whose expansion exceeds the ceiling is refused before the
    expansion happens.
    """

    def __init__(
        self, *, max_expanded_bytes: int, source_game_id: str | None = None
    ) -> None:
        self._values: dict[str, Any] = {}
        self._expanded: dict[str, int] = {}
        self._mentions: dict[str, bool] = {}
        self._max_expanded_bytes = max_expanded_bytes
        # An imported game's payloads are not rewritten when the target differs
        # from the source, so the stale references are counted instead. Counting
        # per blob means repeated content is scanned once, not once per event.
        self._source_game_id = source_game_id

    def __len__(self) -> int:
        return len(self._values)

    def add(self, line_number: int, blob_id: str, raw_value: Any) -> None:
        """Take one ``blob`` record, resolved against the blobs before it."""
        if blob_id in self._values:
            raise BlobTableError(f"line {line_number}: duplicate blob id {blob_id!r}")
        size = self.expanded_size(line_number, raw_value)
        if size > self._max_expanded_bytes:
            raise BlobTableTooLargeError(
                f"line {line_number}: blob {blob_id!r} expands to about {size} "
                f"bytes, over the {self._max_expanded_bytes}-byte ceiling"
            )
        self._values[blob_id] = self.resolve(line_number, raw_value)
        self._expanded[blob_id] = size
        self._mentions[blob_id] = self.mentions_source(raw_value)

    def expanded_size(self, line_number: int, raw_value: Any, depth: int = 0) -> int:
        """Serialized size of what ``raw_value`` describes once resolved.

        Computed from the encoded form and the already-known expanded sizes of
        the blobs it names, so a reference bomb is priced without being built.
        Approximate by a few bytes of punctuation per node, which is all the
        precision a ceiling check needs.

        This is the first walk of every record and every blob, so it is also
        where nesting is bounded: reading a bundle means recursing over
        structure a stranger chose, and Python's stack is the wrong thing to
        find the limit with. Bounding it here means nothing deeper than
        :data:`MAX_NESTING_DEPTH` reaches ``resolve`` or the store, so the
        export side — which only ever walks what the store already holds — needs
        no bound of its own.
        """
        if depth > MAX_NESTING_DEPTH:
            raise BlobTableError(
                f"line {line_number}: value nests deeper than "
                f"{MAX_NESTING_DEPTH} levels"
            )
        if isinstance(raw_value, dict):
            reference = self._reference_id(raw_value)
            if reference is not None:
                return self._expanded[self._require(line_number, reference)]
            # An escaped object's single key is real data, not a marker, so the
            # wrapper is priced as the object it stands for.
            members = self._escaped_inner(line_number, raw_value) or raw_value
            total = 2
            for key, item in members.items():
                total += len(key) + 4 + self.expanded_size(line_number, item, depth + 1)
            return total
        if isinstance(raw_value, list):
            return 2 + sum(
                self.expanded_size(line_number, item, depth + 1) + 1
                for item in raw_value
            )
        if isinstance(raw_value, str):
            return len(raw_value) + 2
        if raw_value is None or isinstance(raw_value, bool):
            return 5
        return len(str(raw_value))

    def resolve(self, line_number: int, raw_value: Any) -> Any:
        """Replace every reference with the value it names."""
        if isinstance(raw_value, dict):
            reference = self._reference_id(raw_value)
            if reference is not None:
                return self._values[self._require(line_number, reference)]
            inner = self._escaped_inner(line_number, raw_value)
            if inner is not None:
                # An escaped payload object: its single key is real data, so it
                # is not interpreted, but its value still holds references.
                return {
                    key: self.resolve(line_number, item) for key, item in inner.items()
                }
            return {
                key: self.resolve(line_number, item) for key, item in raw_value.items()
            }
        if isinstance(raw_value, list):
            return [self.resolve(line_number, item) for item in raw_value]
        return raw_value

    def mentions_source(self, raw_value: Any) -> bool:
        """Whether what ``raw_value`` describes contains the source game id.

        A reference contributes the answer already computed for the blob it
        names, so shared content is scanned once however often it is referenced.
        """
        source = self._source_game_id
        if not source:
            return False
        if isinstance(raw_value, dict):
            reference = self._reference_id(raw_value)
            if reference is not None:
                return self._mentions.get(reference, False)
            members = self._escaped_inner(None, raw_value) or raw_value
            return any(
                source in key or self.mentions_source(item)
                for key, item in members.items()
            )
        if isinstance(raw_value, list):
            return any(self.mentions_source(item) for item in raw_value)
        if isinstance(raw_value, str):
            return source in raw_value
        return False

    @staticmethod
    def _escaped_inner(
        line_number: int | None, value: dict[str, Any]
    ) -> dict[str, Any] | None:
        """The object an escape wraps, or ``None`` when this is not an escape."""
        if len(value) != 1 or next(iter(value)) != LITERAL_KEY:
            return None
        inner = value[LITERAL_KEY]
        if not isinstance(inner, dict):
            raise BlobTableError(
                f"line {line_number}: {LITERAL_KEY!r} must wrap an object, got "
                f"{type(inner).__name__}"
            )
        return inner

    @staticmethod
    def _reference_id(value: dict[str, Any]) -> str | None:
        if len(value) != 1:
            return None
        key = next(iter(value))
        if key != REF_KEY:
            return None
        target = value[REF_KEY]
        return target if isinstance(target, str) else None

    def _require(self, line_number: int, blob_id: str) -> str:
        if blob_id not in self._values:
            raise BlobTableError(
                f"line {line_number}: reference to unknown blob {blob_id!r} "
                "(a reference may only name a blob defined on an earlier line)"
            )
        return blob_id
