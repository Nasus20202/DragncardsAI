## ADDED Requirements

### Requirement: Reclaim failures do not discard an ingest batch
The stream ingester SHALL treat the pending-entry reclaim pass as best-effort. A
failure while reclaiming SHALL NOT prevent the same batch from reading and committing
new entries.

Reclaiming is recoverable by construction: an entry that is not claimed on one cycle
remains in the consumer group's Pending Entries List and stays eligible for a later
cycle once it exceeds `HISTORY_INGEST_CLAIM_MIN_IDLE_MS`. Aborting the batch therefore
costs new events without saving stale ones.

A reclaim failure SHALL be reported as a single warning line naming the exception type
and message, without a stack trace, and SHALL set a `history.reclaim_failed` flag on
the batch span.

A transport failure raised while reclaiming SHALL NOT be interpreted as the
"unknown command" reply that selects the `XPENDING` + `XCLAIM` fallback, because that
signal is a server response and a transport failure is not.

#### Scenario: New entries are still ingested when reclaiming fails
- **WHEN** `XAUTOCLAIM` fails with a connection error and the stream holds an uncommitted entry
- **THEN** `process_batch` SHALL log one warning, read the entry, commit it, acknowledge it, and report it as processed

#### Scenario: Reclaim failure is not mistaken for a missing command
- **WHEN** `XAUTOCLAIM` fails with a transport error rather than an `ERR unknown command` reply
- **THEN** the ingester SHALL NOT switch to the `XPENDING` + `XCLAIM` fallback path

#### Scenario: Unclaimed entries remain available
- **WHEN** a reclaim pass fails and stale entries are left unclaimed
- **THEN** those entries SHALL remain pending and SHALL be claimable on a later cycle

### Requirement: Bounded retry pacing and de-duplicated failure logging
When a whole ingest batch fails, the poll loop SHALL retry with exponential backoff
starting at `INGEST_RETRY_MIN_SECONDS` and doubling to a ceiling of
`INGEST_RETRY_MAX_SECONDS`, rather than retrying on a fixed short delay.

The loop SHALL log a full traceback only for the first failure of a consecutive streak.
Each subsequent failure in the same streak SHALL log a single warning carrying the
count of consecutive failures and the next retry delay.

A batch that succeeds after one or more failures SHALL log a recovery line reporting
how many consecutive failures preceded it, and SHALL reset both the streak count and
the backoff.

Failures that can lose an event SHALL continue to surface: a failing stream read, a
failing commit, a failing acknowledgement and a malformed envelope are unaffected by
this requirement, and no entry is acknowledged without a successful commit.

#### Scenario: A sustained outage backs off instead of spinning
- **WHEN** `process_batch` fails continuously
- **THEN** the delay between attempts SHALL increase monotonically and SHALL NOT exceed `INGEST_RETRY_MAX_SECONDS`

#### Scenario: One traceback per outage
- **WHEN** `process_batch` fails many times consecutively
- **THEN** exactly one log record SHALL carry exception info, and the remainder SHALL be warnings naming the consecutive-failure count

#### Scenario: Recovery resets the pacing
- **WHEN** a batch succeeds after a streak of failures
- **THEN** the ingester SHALL log a recovery line and SHALL return to `INGEST_RETRY_MIN_SECONDS` for any future failure
