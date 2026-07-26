## Why

The Valkey stream consumer in `history-service` reads new entries with `XREADGROUP ... >`, but two durability gaps make it lose events silently in an append-only store:

- `commit_event` runs outside the per-entry error boundary. A transient Postgres error (deadlock, connection blip) propagates out of `process_batch`; `run_forever` logs, sleeps, and loops, and the next `XREADGROUP >` reads only NEW entries. The failed entry — and the un-processed remainder of that batch — stay in the consumer's Pending Entries List (PEL) forever: never re-read, never acked, never committed.
- There is no PEL recovery at all (no `XPENDING`/`XAUTOCLAIM`/`XCLAIM`). The consumer name is `hostname:pid`, so a restarted replica gets a new PID and permanently orphans the crashed consumer's pending entries.

Both paths mean at-least-once delivery silently degrades to "at-most-once with permanent loss".

## What Changes

- **Per-entry failure isolation**: wrap each entry's commit so a transient failure is logged and the entry is left UN-acked (so it stays pending for reclaim) while the rest of the batch continues. Malformed/undecodable entries keep their existing acked-and-dropped behavior.
- **PEL recovery**: on each poll cycle, reclaim stale pending entries with `XAUTOCLAIM` (falling back to `XPENDING` + `XCLAIM` when the server predates autoclaim), gated by a new `HISTORY_INGEST_CLAIM_MIN_IDLE_MS` config knob (default 30000). Reclaimed entries are re-run through the same idempotent commit path; because commits dedupe on `(game_id, idempotency_key)`, re-processing a duplicate is safe and never consumes a `seq`.
- Snapshot-after-commit stays best-effort: a snapshot failure never blocks the ack.

## Impact

- `services/history-service/src/history_service/runtime/ingest.py`: per-entry isolation, `reclaim_pending` (+ fallback).
- `services/history-service/src/history_service/config.py`: `history_ingest_claim_min_idle_ms` setting.
- `services/history-service/tests/unit/test_ingest.py`: tests for failure isolation and PEL reclaim.
- No database schema changes.
