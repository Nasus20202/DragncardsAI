## 1. Establish what the traceback actually means

- [x] 1.1 Confirm `resp.py` line 145 on this branch is the guarded `await writer.wait_closed()`
- [x] 1.2 Confirm the whole tree, `external/` included, contains exactly one `resp.py` and that neither call site overrides `execute`
- [x] 1.3 Confirm `dragncards_common` resolves to the source file in a service venv, ruling out a shadowing non-editable copy
- [x] 1.4 Reproduce the reported traceback at the socket level with `SO_LINGER`-forced RST against the committed code
- [x] 1.5 Prove the mechanism by exception identity: the object raised in `_read_resp` is the object escaping `execute()`
- [x] 1.6 Refute `6a4972e` (DRA-23) as the regression boundary by diffing its `ingest.py` and `valkey.py` changes

## 2. Fix the traceback misattribution in the shared client

- [x] 2.1 Set `skip_wait_closed = True` on the error path in `execute`
- [x] 2.2 Keep `writer.close()` on every path so the socket is still released
- [x] 2.3 Leave the success path awaiting the close waiter, still guarded
- [x] 2.4 Add a socket-level test that a reset after a complete reply still returns the value
- [x] 2.5 Add a socket-level test that a mid-command reset blames `_read_resp` and not `wait_closed`
- [x] 2.6 Verify the new test fails without the fix and passes with it

## 3. Stop one failed command from discarding an ingest batch

- [x] 3.1 Guard the `reclaim_pending()` call in `process_batch` and continue to `XREADGROUP`
- [x] 3.2 Log the reclaim failure as a single warning line, not a traceback
- [x] 3.3 Record a `history.reclaim_failed` span flag and permit it in the pinned attribute allowlist
- [x] 3.4 Confirm a failing `XAUTOCLAIM` raised as a transport error is not mistaken for the `XPENDING` fallback signal
- [x] 3.5 Add a regression pin that the batch still commits and acks its entry when reclaim fails

## 4. Bound the retry loop and its log volume

- [x] 4.1 Add `INGEST_RETRY_MIN_SECONDS` / `INGEST_RETRY_MAX_SECONDS` and exponential backoff
- [x] 4.2 Log one traceback for the first failure of a streak, counted warnings thereafter
- [x] 4.3 Log a recovery line and reset the backoff when a batch succeeds again
- [x] 4.4 Add a regression pin asserting growing delays and exactly one traceback per outage
- [x] 4.5 Measure log volume before and after over a fixed failure window

## 5. De-noise the recoverable model-cache warnings

- [x] 5.1 Drop `exc_info=True` from the four `BifrostClient` cache warnings
- [x] 5.2 Confirm both readers still fall through to a live Bifrost fetch on a cache transport error

## 6. Verify

- [x] 6.1 `./scripts/lint.sh --fix` then `./scripts/lint.sh` exits 0
- [x] 6.2 `./scripts/test.sh unit` — record per-service counts against the baseline
- [x] 6.3 Identify the `test_a_chat_session_still_spawns_a_memoryless_child` flake and confirm it also fails on the clean baseline
- [x] 6.4 `./scripts/test.sh integration history-service` and `... agent-orchestrator`
- [x] 6.5 `openspec validate dra-35-connection-errors --strict`
- [x] 6.6 `openspec validate --all`, expecting only the pre-existing `spec/typed-game-actions` failure
- [x] 6.7 Grep the change directory for placeholder markers
- [x] 6.8 Measure per-command TCP connection churn to size the pooling follow-up
