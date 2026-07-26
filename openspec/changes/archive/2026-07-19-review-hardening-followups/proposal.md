# Review hardening follow-ups

## Why

Post-implementation review (code-review, security-review, and simplify) of the
service-hardening + `dragncards-common` shared-library batch surfaced a small
set of follow-ups worth addressing before the work is considered done:

- **Security (MEDIUM)** — the `conversation_context` limits on
  `/sessions/restore` are enforced only *after* the ASGI server has buffered and
  JSON-parsed the entire request body, and there is no upstream body-size cap.
  A large (or deeply nested) body can therefore exhaust memory before the
  validator ever rejects it, so the validation is a shape/content boundary but
  not a resource-exhaustion boundary.
- **Security (LOW)** — the newly-shared `dragncards_common.resp` parser applies
  no upper bound to `$` (bulk string) / `*` (array) length prefixes, so a
  malformed or hostile reply could drive an unbounded read/allocation or deep
  recursion. Trusted Valkey traffic today, but the parser is now a reusable
  shared component.
- **Correctness (latent)** — the agent-orchestrator `RespConnection` subclass
  drops the `tracer` keyword, so the inherited `from_url` classmethod (which
  forwards `tracer=`) would raise `TypeError` if ever used on the subclass.
- **Correctness (latent)** — a sub-second Bifrost negative-cache TTL rounds to
  `0`, silently disabling that cache tier instead of caching for ~1s.
- **Simplification** — the shared `CollapsibleCard` carries a `defaultOpen` prop
  that no call site uses.

## What Changes

- **agent-orchestrator (request body cap)** — add a pure-ASGI
  `MaxBodySizeMiddleware` that rejects a declared oversized `Content-Length`
  up front and otherwise buffers a streamed body only up to a configured
  `MAX_REQUEST_BODY_BYTES` (default 8 MiB), returning `413` before the
  application reads the body; within-limit bodies are replayed unchanged.
- **dragncards-common (RESP bounds)** — `_read_resp` SHALL reject `$`/`*` length
  prefixes that are negative (other than the `-1` nil sentinel) or exceed a
  fixed ceiling, raising `RespError` instead of reading unboundedly.
- **agent-orchestrator (RESP from_url)** — the subclass `__init__` accepts an
  optional `tracer`, defaulting to the module tracer, so `from_url` works.
- **agent-orchestrator (TTL rounding)** — a positive Bifrost cache TTL never
  rounds down to `0`; only a non-positive value disables the tier.
- **dashboard (CollapsibleCard)** — remove the unused `defaultOpen` prop.

## Out of scope (pre-existing, flagged for a separate change)

- A ~500-line duplicated (shadowed) test block in
  `agent-orchestrator/tests/unit/test_bifrost.py` predates this batch (present
  at the batch's base commit) and is left untouched here.
- The `BifrostClient._extract_error_message` thin delegate and two pre-existing
  dead `*_seconds` float fields remain, being entangled with those pre-existing
  duplicated tests.
