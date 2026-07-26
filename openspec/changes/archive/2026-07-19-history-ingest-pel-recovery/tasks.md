## 1. Per-entry failure isolation

- [x] 1.1 Wrap `commit_event` in `_handle_entry` so a transient failure is logged and the entry is left un-acked (not acked) without aborting the batch
- [x] 1.2 Keep malformed/undecodable entries acked-and-dropped
- [x] 1.3 Keep snapshot-after-commit best-effort so a snapshot failure never blocks the ack

## 2. PEL recovery

- [x] 2.1 Add `HISTORY_INGEST_CLAIM_MIN_IDLE_MS` config knob (default 30000, non-negative validator)
- [x] 2.2 Add `reclaim_pending` using `XAUTOCLAIM` with the min-idle gate, re-processing claimed entries through the idempotent commit path
- [x] 2.3 Fall back to `XPENDING` + `XCLAIM` when the server lacks `XAUTOCLAIM`
- [x] 2.4 Call `reclaim_pending` on each poll cycle before reading new entries

## 3. Testing

- [x] 3.1 Test that a commit failure on one entry does not lose the others and leaves the failed one un-acked (pending)
- [x] 3.2 Test that stale pending entries are reclaimed and committed on a later cycle
- [x] 3.3 Test the `XPENDING`/`XCLAIM` fallback path
- [x] 3.4 Run `uv run pytest tests/unit` and `./scripts/lint.sh --fix` — all pass

## 4. Spec sync

- [x] 4.1 Modify the `Dual-source idempotent ingestion` requirement with transient-failure-isolation and PEL-reclaim scenarios
- [x] 4.2 `openspec validate history-ingest-pel-recovery --strict` passes
