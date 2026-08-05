# Tasks

## 1. Bundle format version 2: the codec

- [x] 1.1 Add `BUNDLE_FORMAT_VERSION = 2`, `BUNDLE_SUPPORTED_FORMAT_VERSIONS = (1, 2)`,
      `BundleMode` (`full` | `minimal`), `MINIMAL_OMITTED_PAYLOAD_FIELDS`, the
      `$ref`/`$literal` markers and the 256-byte dedup threshold to
      `services/history-service/src/history_service/schemas/transfer.py`
- [x] 1.2 Add `mode` and `omitted_payload_fields` to `BundleHeader` (defaulting to
      `full`/`[]` so a version 1 header validates), and `blob_count` to
      `BundleFooter` (defaulting to 0 for version 1). **Not** to the header: blobs
      are discovered while the export streams, so a header written first could
      only carry a count by buffering the whole bundle, which is the one thing
      the format refuses to do
- [x] 1.3 Add a `BundleBlob` record model (`kind`, `id`, `first_seen`, `value`)
- [x] 1.4 Write `runtime/bundle_codec.py`: a `BlobWriter` that walks a value,
      extracts every dict/list at or above the threshold into blob records with
      backward-only `{"$ref": …}` substitution, escapes `$ref`/`$literal`
      collisions as `{"$literal": …}`, and assigns `b<N>` ids in first-encounter
      order so output is deterministic
- [x] 1.5 Write the matching `BlobTable` reader: resolve refs against already-read
      blobs, reject an unknown or forward id, unwrap `$literal`, and track each
      blob's expanded size so a reference bomb is refused
- [x] 1.6 Unit-test the codec: dedup of repeated values, nested blobs, a growing
      prefix list, determinism (same input → identical bytes), `$ref` and
      `$literal` present in real payload data, unknown ref id, forward ref, and a
      reference bomb refused against a small ceiling
- [x] 1.7 Bound how deeply a read value may nest (200 levels), enforced where the
      expansion is priced, so a hand-built file cannot recurse this process into a
      `RecursionError` and a 500. Reading-side only: nothing deeper can then reach
      the store for an export to walk
- [x] 1.8 Never extract the payload root, only its members — an extracted root
      leaves a record line reading `"payload": {"$ref": "b7"}`, which says nothing
      about the record and measures 5 078 bytes *larger* on the real game. A root
      that is itself a marker object is still escaped, because that is
      correctness rather than compression

## 2. Export: modes and blobs

- [x] 2.1 Give `iter_export_lines` a `mode` parameter; emit blob records ahead of
      the first record that references them, and carry `mode`,
      `omitted_payload_fields` and `blob_count` in the header
- [x] 2.2 Emit `blob_count` in the footer, counted as the export streams
- [x] 2.3 Elide `agent_move.payload.conversation_context` in `minimal` mode, by
      removing the key rather than emptying it
- [x] 2.4 Add `mode` as a validated query parameter on `GET /games/{game_id}/export`,
      defaulting to `full`, and reflect the mode in the download filename
- [x] 2.5 Unit-test export: a full bundle is byte-identical across two exports, a
      minimal bundle omits exactly the one field and declares it, an unknown game
      still exports a header/footer pair, and a bad `mode` is a 422

## 3. Import: blob resolution and version 1 compatibility

- [x] 3.1 Teach `BundleReader` the `blob` record kind, resolving `event` and
      `snapshot` payloads through the blob table as they are read
- [x] 3.2 Accept `format_version` 1 and 2; reject a `blob` record inside a version 1
      bundle with a message naming the line
- [x] 3.3 Validate `blob_count` in the footer against the blobs actually read, and
      reject a `full` header that declares omitted fields
- [x] 3.4 Count events whose resolved payload mentions the source `game_id`,
      scanning each blob once rather than once per reference — including in a
      version 1 bundle, which has the same provenance question and no blobs
- [x] 3.5 Unit-test import: a version 2 round trip, a version 1 bundle still
      importing, a blob in a version 1 bundle rejected, a footer `blob_count`
      mismatch rejected, and the reference count reported

## 4. "Import as"

- [x] 4.1 Add `as_new` to `POST /import`; when true, mint a `uuid4` target
- [x] 4.2 Reject `game_id` and `as_new` together with a 400 naming both
- [x] 4.3 Add `mode` and `source_id_references` to `ImportResponse`
- [x] 4.4 Unit-test: `as_new` never collides and never 409s, the combination is a
      400, the explicit target still works, the default target still 409s on an
      occupied id, and the 409 message names the alternatives

## 5. Round-trip fidelity

- [x] 5.1 Unit test: export → import (new id) → export produces a byte-identical
      `full` bundle apart from `exported_at` and the header `game_id`
- [x] 5.2 Unit test: the same for `minimal`, pinning the loss exactly — the only
      difference from the full round trip is that `agent_move` payloads have no
      `conversation_context` **key**, asserted as absence rather than emptiness
- [x] 5.3 Unit test: a payload carrying `$ref`, `$literal`, non-ASCII text and deep
      nesting survives a round trip unchanged
- [x] 5.4 Integration test (Postgres): export a seeded game, import it under a
      server-minted id, and compare every stored event and snapshot field —
      including a marker object, which has to survive JSONB as well as the codec

## 6. The restore path a minimal bundle lands on

- [x] 6.1 Report an empty captured conversation as an agent context that was **not**
      restored, with a reason naming the `minimal` export, instead of seeding the
      orchestrator with `[]` and reporting success
- [x] 6.2 Unit-test that a minimally imported game restores its game state and
      replays the same events as the fully exported game, and reports
      `agent_context_restored: false`

## 7. Dashboard

- [x] 7.1 Extend `historyExportUrl` with a mode, and `importHistoryBundle` with
      `asNew`; add `mode` and `source_id_references` to `HistoryImportResult`
- [x] 7.2 Replace the bare import button with a dialog offering the three targets —
      the bundle's own id, a new id the server mints (default), or a typed id — and
      an export mode choice on the export control
- [x] 7.3 Report the mode in the success notice, and when the target differs from
      the source and references remain, say how many events still name the source
- [x] 7.4 Extend the existing transfer tests for the dialog, each target, the
      mode choice, and the notice wording

## 8. Documentation and verification

- [x] 8.1 Update `services/history-service/README.md` with the format version 2
      record kinds, the modes, the import targets, and the measured sizes
- [x] 8.2 Update the transfer router and schema docstrings, which are the OpenAPI
      descriptions the dashboard's Swagger view renders
- [x] 8.3 Verify against a real recorded game: export the running stack's
      124-event game, re-import it into a throwaway history-service and store,
      export it in both modes, measure all three, and re-import each
- [x] 8.4 Drive the export and import dialogs end to end in a browser, including
      the 409 that keeps the dialog open and the notice that names the remaining
      source references
- [x] 8.5 `./scripts/lint.sh --fix`, `./scripts/test.sh unit`,
      `./scripts/test.sh integration`, `openspec validate --all`
