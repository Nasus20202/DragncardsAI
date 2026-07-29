## ADDED Requirements

### Requirement: Recoverable model-cache failures log without a stack trace
A Valkey transport failure in the `BifrostClient` model cache SHALL be logged as a
single warning line naming the exception type and message, and SHALL NOT be logged with
exception info.

The model cache is an optimisation. Every reader already falls through to a live
Bifrost fetch when a read misses, so a transport failure changes latency and nothing
else. Emitting a stack trace presented a fully handled condition as a crash and
contributed to the log flood reported in DRA-35.

This requirement governs logging only. The existing degradation behaviour SHALL be
unchanged: a failed cache read SHALL still return no value and SHALL still allow the
caller to fetch live, and a failed cache write SHALL still be non-fatal.

#### Scenario: A failed cache read degrades quietly to a live fetch
- **WHEN** a cache read raises a connection error during `list_models`
- **THEN** the client SHALL log one warning without exception info and SHALL fetch the listing live from Bifrost

#### Scenario: A failed cache write does not fail the request
- **WHEN** a cache write raises a connection error after a successful live fetch
- **THEN** the client SHALL log one warning without exception info and SHALL return the fetched listing
