# Tasks

## 1. Separate the two candidate defects by measurement, before changing anything

- [x] 1.1 Enumerate every Valkey call site in agent-orchestrator: `live_events.py`
      (`XREAD`, `XADD`, `EXPIRE`), `history_emitter.py` (`INCR`, `XADD`),
      `integrations/bifrost.py` (`GET`, `SETEX`, `DEL`). Confirm all of them route
      through `storage/valkey.py`, which injects the service tracer, so every
      command is spanned.
- [x] 1.2 Read `services/shared/src/dragncards_common/resp.py` (read only — the
      file is owned elsewhere) and record the two properties that make this issue
      what it is: `asyncio.open_connection` inside `execute()`, and one
      `valkey.execute` span per command when a tracer is present.
- [x] 1.3 Query the running stack's `agent-orchestrator-valkey` read-only
      (`INFO commandstats`, `INFO stats`, `DBSIZE`, `SCAN`) on host port 6381.
      Record: 40,442 commands processed against 40,454 connections received over
      15,760s uptime, and the per-command breakdown.
- [x] 1.4 From that breakdown, establish that ~416 of 40,442 commands (1.0%) did
      work and the rest is three idle loops — history-service's consumer triple
      (78.6%), the orchestrator's SSE `XREAD` (12.6%), Docker's healthcheck `PING`
      (7.8%). Note `xadd:78` vs `expire:1` proves this is the idle floor, not a
      busy period.
- [x] 1.5 Build a harness that fakes `asyncio.open_connection` so the real RESP
      client runs unmodified, and count commands, TCP connections and spans per
      representative operation.
- [x] 1.6 Record the verdict from 1.3 and 1.5 together: commands = connections =
      spans, 1:1:1. Therefore (b) is a faithful mirror of (a), not an independent
      defect, and no span-level measure can reduce the spans without leaving the
      commands and connections in place. **(a) dominates.**
- [x] 1.7 Retire the DRA-23 hypothesis explicitly: it began injecting the tracer,
      so it is why the volume is visible, but the 1:1 result shows it changed
      nothing about the volume.
- [x] 1.8 Reconcile the arithmetic with the reported trace: `start_span` inherits
      ambient context, so an SSE request's command spans are children of that one
      request span; at ~3 spans per tick and 5 ticks/second, 6,000 spans is ~7
      minutes of one open stream. Confirms the reported number against a mechanism.

## 2. Give the SSE stream its own fallback interval

- [x] 2.1 Add `job_event_stream_idle_block_seconds` (default 15.0, alias
      `JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS`) with a positive-value validator, and
      a comment recording why it must not be `worker_poll_interval_seconds`.
- [x] 2.2 Rename `JobEventStreamService`'s parameter from `poll_interval_seconds`
      to `idle_block_seconds` and document on the class that it is a fallback
      interval, not a latency budget.
- [x] 2.3 Wire it in `runtime/app.py` from the new setting instead of the worker
      tick.
- [x] 2.4 Unit-test that the setting defaults to 15.0, is not equal to the worker
      poll interval, accepts the environment alias, and rejects zero.

## 3. Stop the close path paying an interval it does not need

- [x] 3.1 Make the loop continue to its final database pass when the terminal
      event has already been delivered, instead of blocking on the live bus first.
      Without this, task 2 would have turned closing such a stream into a
      15-second hang.
- [x] 3.2 Unit-test it with `idle_block_seconds=600.0` under a 5-second
      `asyncio.timeout`, so the test fails by timing out if the wait returns.

## 4. Make publishing one live event cost one command

- [x] 4.1 Replace `XADD` + `EXPIRE` with a single `EVAL` performing both, passing
      the stream key as `KEYS[1]` rather than interpolating it, and returning the
      entry id `XADD` returned.
- [x] 4.2 Record in a comment why the TTL must be re-armed on every append — a
      job quiet longer than the TTL loses its stream, and the next append recreates
      the key with no expiry and leaks it — so nobody thins it out later.
- [x] 4.3 Unit-test that publishing issues exactly one command, that the script
      contains both operations, that the key arrives as a declared `KEYS` entry,
      and that the returned event carries the id and payload.
- [x] 4.4 Execute the script against the real Valkey 9.1.1 in the running stack on
      a throwaway key: verify entry ids match what `publish` returned, `XLEN` is 3,
      `TTL` is set, all three read back in order with intact payloads, then delete
      the key.

## 5. Make a subscriber read a batch per command

- [x] 5.1 Change `XREAD ... COUNT 1` to `COUNT 64` and buffer the surplus in the
      subscriber, serving `get()` from the buffer before issuing another read, so
      the public one-event-at-a-time contract is unchanged.
- [x] 5.2 Advance `_last_id` per entry as entries are buffered, so a later read
      resumes from the last entry handed out rather than replaying the batch.
- [x] 5.3 Drop the buffer in `aclose()`, and document that it is request-scoped —
      one subscriber per SSE request or subagent wait — and therefore not the
      process-lifetime state the repository forbids.
- [x] 5.4 Thread the batch size from the bus so it is configurable at the seam it
      belongs to, without adding a service setting for it.
- [x] 5.5 Unit-test that three events arrive on one `XREAD`, that the next read
      reaches Valkey only once the buffer empties and resumes from the last entry
      handed out, and that the buffer is dropped with the subscription.

## 6. Audit what a longer interval strands, and publish it

- [x] 6.1 Rebase onto the integration tip. Resolve `runtime/live_events.py` as a
      union: DRA-34's optional `durable_event_id` stream field has to travel
      *inside* the single `EVAL`, so the script takes its field/value pairs as a
      variable-length `ARGV` tail instead of fixed positions — one script for both
      shapes, no branch, no extra command.
- [x] 6.2 Re-verify the reworked script against the real Valkey 9.1.1 on a
      throwaway key, publishing with and without `durable_event_id`: entry ids match
      what `publish` returned, `XLEN` 3, `TTL` 120, all three read back in order,
      and an absent field decodes as `None`. Delete the key.
- [x] 6.3 Audit all 26 `append_event` call sites against the publishes beside them
      and record the result as a table in `design.md`. Finding: three `cancellation`
      sites (`request_cancel` for the job *and* each active child, plus
      `mark_job_cancelled`) and four tool-event sites (`tool_call`, `tool_result`,
      and both rows of the invalid-call path) are durable with no publish — the tool
      events were never published by any path at all.
- [x] 6.4 Establish the severity ordering instead of assuming the reported case is
      the worst. `cancellation` is terminal, so an unpublished one leaves the stream
      *open*, and for a queued job `request_cancel`'s append is the only
      announcement that will ever exist. `tool_call` is recorded *before* the tool
      runs, exactly when the bus falls quiet, so a slow tool would show nothing at
      all — that class is the more frequent.
- [x] 6.5 Before adding any publish, verify the dashboard would render these once
      and not twice: `upsertStreamEvent` de-duplicates on the payload `id`, both
      tool types are already on the SSE allowlist, and handing one `payload` dict to
      both `append_event` and `publish` makes the second copy an identity-preserving
      no-op. No dashboard change needed.
- [x] 6.6 Return the durable id from both cancellation writers —
      `mark_job_cancelled` returns the appended row's id (its two callers never used
      the `Job`, so nothing else moves) and `request_cancel` returns an
      `AppendedCancellation` per affected job — and publish under those ids from all
      four call sites: both `prompt_run` cancel checks, the cancel endpoint and
      session delete.
- [x] 6.7 Publish `tool_call` and `tool_result` with their durable ids at all four
      sites, handing the same payload dict to both calls so the copies compare equal.
- [x] 6.8 Leave `progress {"status": "running"}` on the fallback pass and say so:
      not terminal, so it cannot hold a stream open, and the same fact is already on
      the job row the dashboard renders from.
- [x] 6.9 Add the latency tests. One drives a cancellation into an open stream with
      the interval at 600s under a 5s timeout, so it fails rather than merely slows
      if the publish is dropped or the interval is rewired to the worker tick; one
      asserts the run publishes the cancellation it persists, under the durable id;
      one asserts `request_cancel` reports an id per affected job.
- [x] 6.10 Mutation-check the first of those: delete the `prompt_run` publish and
      confirm the test fails, restore it and confirm it passes. A latency test that
      cannot fail is worthless.
- [x] 6.11 Record the audit as a spec requirement so the rule outlives this change:
      an event a client waits on is published with its durable id, and one
      deliberately left to the fallback pass is written down as such.
- [x] 6.12 Verify the whole path end to end against the real Valkey, not only in
      unit tests: drive the real cancel route, repository, `ValkeyLiveEventBus`,
      subscriber and SSE generator with the interval at the shipped 15s and the job
      left queued. Result **72 ms** from `POST /cancel` to the cancellation frame,
      one durable row, frame carrying that row's id.
- [x] 6.13 Run the same end-to-end check with the route's publish deleted, to
      confirm the regression was real and the fix is what closes it: **14,144 ms**.
      Restore the file and confirm the tree is clean.

## 7. Confirm the effect and that nothing regressed

- [x] 7.1 Re-run the harness against this branch and against `HEAD` via
      `git archive`, so before and after are measured by the same code: idle stream
      5.0 → 0.067 commands/second (75×), publish ×100 200 → 100 (2×), a 500-delta
      turn with one viewer 1,500 → 508 (2.95×), with two viewers 2,000 → 516
      (3.88×).
- [x] 7.2 Confirm commands = connections = spans still holds after the change, so
      the reduction is real and not an artefact of counting.
- [x] 7.3 Run the agent-orchestrator unit suite: 500 passing (490 baseline plus the
      10 tests added here), with only the known `test_player_seat_sessions` flake,
      confirmed green in isolation.
- [x] 7.4 Run `./scripts/lint.sh --fix` and the full `./scripts/test.sh unit`
      across every service, and confirm `openspec validate --all` reports only the
      one pre-existing `spec/typed-game-actions` failure.

## 8. Keep the ancillary files honest

- [x] 8.1 Add `JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS` to
      `services/agent-orchestrator/.env.example` with the reason it is measured in
      seconds rather than milliseconds.
- [x] 8.2 Add a "Valkey command volume on the streaming path" section to the
      agent-orchestrator README stating the three properties and what each cost
      before, since each is a one-line edit away from being undone.
- [x] 8.3 Record in that same README section the rule the audit produced — a
      durable event with no publish is now late by the idle interval rather than by
      200ms — so the next person to append an event knows to publish it.
- [x] 8.4 Confirm no compose, OTel or script change is needed: the default is
      correct everywhere and nothing overrode the old value.

## 9. Write down what was found but deliberately not fixed

- [x] 9.1 Record the transport finding in `design.md` as a coordination item —
      one TCP connection per command is the multiplier under all of this, it is
      already filed with DRA-35's measurements, and the call-site view is that one
      streamed turn still opens ~508 avoidable connections after this change.
- [x] 9.2 Record history-service's ingest loop with its numbers: 78.6% of all
      commands on this Valkey, three commands per ~2s idle cycle of which two do
      no work, and the reason it is not fixed here.
- [x] 9.3 Record the dashboard's stream multiplication: 11-12 concurrent streams
      for a 10-subagent fan-out, stale `running` entries holding streams
      indefinitely, and `after=0` full replay on reconnect because the endpoint
      ignores `Last-Event-ID`.
- [x] 9.4 Record why span sampling and filtering were rejected, and note that no
      sampler is configured anywhere in the repository today, so those levers stay
      available once command volume is proportionate.

## 10. Reconcile with DRA-42, which merged after this change was written

- [x] 10.1 Rebase onto the integration tip and run the agent-orchestrator unit
      suite to find the damage rather than predicting it: 5 failures, all in
      DRA-42's `test_live_event_resilience.py`, 508 passing.
- [x] 10.2 Confirm the two guards on the stream's live read coexist rather than
      conflict: DRA-42's `try/except` around `live_subscriber.get` sits directly
      under this change's terminal-close shortcut, on a different branch of the
      same loop, and both are kept. Record why dropping either reintroduces a bug.
- [x] 10.3 Delete DRA-42's `try/except` around the `EXPIRE`, as DRA-42's own
      design marked it delete-on-rebase: the single `EVAL` leaves no window
      between the append and the refresh for that guard to cover.
- [x] 10.4 Restate the requirement that guard satisfied as a `MODIFIED` spec
      requirement about atomicity, so the guarantee survives its implementation
      being replaced by a stronger one.
- [x] 10.5 Retarget DRA-42's two TTL tests at the shape that now exists: one
      pinning that no separate `EXPIRE` command is issued at all, one pinning that
      a failing append still raises and that `BestEffortLiveEventBus` is what
      turns it into `None`.
- [x] 10.6 Check every place a test captures a `publish` return value, since
      DRA-42 retyped it `LiveJobEvent | None` and wraps every bus the service
      hands out — an assertion on the return value would now pass vacuously. All
      three sites build a bare bus and assert on the delivered copy instead; no
      change needed, and the finding is recorded in `design.md`.
- [x] 10.7 Record the residual neither change could see alone — a publish that
      fails while the same stream's reads succeed leaves a terminal event waiting
      out the 15s block — in `design.md`, with the reasons it is accepted and the
      reason shortening the interval to cover it is refused.
- [x] 10.8 Note in `design.md` that this change is what makes DRA-42's own
      "degrading never increases latency" requirement true: its 0.5–5s degraded
      range was above the 0.2s healthy block it shipped against, and sits below
      the 15s one.
