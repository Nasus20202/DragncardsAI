# Tasks

DRA-12 started as a proposal. The owner approved sections **(A)** and **(C)** and
withheld sign-off on **(B)**, so (A) and (C) are implemented here and (B) is
deliberately untouched: the auto-compaction trigger still measures the replay
only, and `CONTEXT_COMPACTION_THRESHOLD` is still `0.8`.

Two approval gates, because the two halves carry different risk:

- **Gate 1 — section (A)**: bounds an unbounded LLM request and stops a
  compaction failure from failing the user's turn. Fixes a fault; changes nothing
  about a healthy turn. Sections 2-4 below. **Approved and implemented.**
- **Gate 2 — section (B)**: changes *when* history is summarised, so it changes
  what the model sees on some turns. Needs the owner's explicit sign-off,
  separately from Gate 1. Sections 5-6 below. **Not approved; section 5 is not
  implemented and remains a live proposal.** Section 6 is (C), which was approved
  and is implemented.

Section 1 is verification of the baseline. Section 7 closes out.

## 1. Re-confirm the baseline before changing it

- [x] 1.1 Confirm `perform_compaction` still passes `after_job_id=None` and so
      re-reads every job from session start
      (`services/agent-orchestrator/src/agent_orchestrator/runtime/compaction.py:120-124`).
      Confirmed, with the comment "Get everything (compaction covers it all)".
- [x] 1.2 Confirm `maybe_auto_compact` is still awaited unguarded inside the job's
      `try` (`runtime/prompt_run.py:206-207`, handlers at `:567`/`:578`), so a
      compaction exception marks the job failed. Confirmed.
- [x] 1.3 Confirm the trigger still estimates the replay only
      (`prompt_run.py:857-860`) while the metadata endpoint estimates system
      prompt + replay + tools (`runtime/session_transcript.py:160-186`).
      Confirmed, and still true after this change: (B) was not approved.
- [x] 1.4 Confirm inlined skill content still lives only in the model's copy of
      the user message and never in the stored prompt
      (`runtime/skills.py:195-232`, `prompt_run.py:220-229`), so replay is
      unaffected by DRA-15. Confirmed.
- [x] 1.5 Reproduce the defect end-to-end rather than trusting the reading: drive
      a session long enough to auto-compact, with the compaction call forced to
      exceed the window, and record that the user's turn fails. Reproduced as an
      executable test rather than by hand: a provider fake that rejects any
      summarization request larger than the window marked the user's turn
      `failed` with `context_length_exceeded` against the unguarded code. That
      test is now the regression test for 2.1.

## 2. (A4) Stop a compaction failure from failing the turn — ship this first

- [x] 2.1 Wrap the `maybe_auto_compact` call at `prompt_run.py:206-207` so no
      exception from it escapes into the job's failure handlers. Implemented
      inside `maybe_auto_compact` itself, so the usage ratio that triggered the
      attempt is in scope for the log line and the event.
- [x] 2.2 Treat `perform_compaction`'s two `ValueError` cases — "No completed jobs
      to compact" (`compaction.py:111`) and "No history content to compact"
      (`:163`) — as no-ops that log at info and emit nothing. Both now raise
      `NothingToCompactError`, a `ValueError` subclass, so the two cases are told
      apart by type instead of by matching the message text.
- [x] 2.3 Emit a `compaction_failed` job event for a real failure, carrying the
      failure message and the usage ratio that triggered the attempt. Carries
      `code`, `message` and `usage_ratio`, and is both persisted and published.
      Recording it is itself guarded: a job that survived a failed compaction
      must not die reporting it.
- [x] 2.4 Add `compaction_failed` to `STREAM_EVENT_TYPES`
      (`services/dashboard/features/play/lib/play-session-events.ts:63-79`) and
      render it in the transcript alongside the existing `compaction` block
      (`features/play/components/play-transcript.tsx:140-150,266`). No migration:
      `job_events.event_type` is a free string. Rendered in warning rather than
      danger styling, saying the turn continued — the `failure` row's danger
      styling would misreport a degradation as a dead turn.
- [x] 2.5 Update `services/agent-orchestrator/AGENTS.md`'s event-type list, which
      enumerates every job event type. Also added to the README's event list and
      to a new README "Context Management" section.
- [x] 2.6 Orchestrator unit tests: a failing summarizing call leaves the job
      completed and emits `compaction_failed`; a session with no completed job
      emits nothing and completes; the manual endpoint still returns an error for
      the same failure (502, asserted).
- [x] 2.7 Dashboard unit test: the transcript renders a `compaction_failed` event,
      and the event type is present in `STREAM_EVENT_TYPES`.

## 3. (A1) Checkpoint the compaction input

- [x] 3.1 Pass `after_job_id=existing_compaction.covers_up_to_job_id` in
      `perform_compaction` when a previous record exists, matching what
      `build_message_history` already does
      (`runtime/session_transcript.py:88-93`). Keep the previous summary in the
      request — it is what makes the checkpoint safe.
- [x] 3.2 Add a "from session start" mode to `POST /sessions/{session_id}/compact`
      that ignores the checkpoint, so a user can rebuild a summary they believe
      lost information. Automatic compaction always uses the checkpointed form.
      Implemented as an optional `CompactSessionRequest` body with
      `from_session_start`, so existing bodyless callers are unaffected.
- [x] 3.3 Expose that mode in the dashboard only if it is free to do so; a
      request body flag with no UI is acceptable for a recovery path. Do not add a
      second button to the context widget for it. No dashboard change was made.
      The flag is reachable from the generated MCP `compact_session` tool and from
      any HTTP caller.
- [x] 3.4 Orchestrator unit tests: a second compaction's input contains the
      previous summary and only post-checkpoint jobs; the from-start mode contains
      every eligible job; the first compaction of a session is unchanged. Also
      that a second compaction with no new job is a no-op rather than a
      re-summarisation.
- [ ] 3.5 Measure the drift risk the design names as its one open question:
      compact the same long session under both modes and diff the summaries for
      dropped tracked state (hero HP, threat, villain phase, cards in play).
      Not done, and deliberately left open: it needs two real summarizing calls
      over one long game, and the deployment has no `CompactionRecord` at all yet,
      so there is no summary to diff against. The `from_session_start` mode the
      diff requires now exists, which is what makes the measurement cheap once a
      long game is available. Record the result on DRA-12 whichever way it comes
      out — a checkpointed summary that loses state is a reason to revisit, and a
      clean diff is the evidence that closes the question.

## 4. (A2, A3) Bound the compaction input's size

- [x] 4.1 Add a per-event character budget applied separately to a tool call's
      arguments text and a tool result's content text in
      `compaction.py:141-171`, appending an explicit `… [truncated, N chars
      omitted]` marker where text is cut.
- [x] 4.2 Add the budget as a setting alongside the existing context settings in
      `config.py:121-130`, with a default of 20 000 characters and a validator
      requiring it to be positive. `CONTEXT_COMPACTION_EVENT_CHAR_BUDGET`, with
      the default named once as `COMPACTION_EVENT_CHAR_BUDGET_DEFAULT` so the
      compaction module and the settings class cannot disagree.
- [x] 4.3 Validate that default against a real game before merging: instrument the
      character length of `arguments` and `result` per tool across one full
      session and confirm the budget sits above the 99th percentile of
      `get_game_state`. Measured against the running deployment's `job_events`
      rather than a fresh game: `get_game_state` (n=147) reaches 6,307 characters
      at the maximum and 6,299 at the 99th percentile, against a 20,000 budget.
      The payloads over the budget are `get_raw_game_state_games` (498,056),
      `get_session_actions` (58,295), `search_cards_marvel_champions` (50,003),
      `search_prebuilt_sets_marvel_champions` (36,023) and `list_actions`
      (34,881). Arguments peak at 807 characters. The default stands.
- [x] 4.4 Estimate the assembled summarization request with
      `estimate_tokens_for_messages` — already imported and unused at
      `compaction.py:12` — and drop history entries oldest-first while it exceeds
      `window × CONTEXT_COMPACTION_THRESHOLD`. The fixed part of the request is
      estimated once and each entry costed once, rather than re-estimating the
      whole request per drop, which would be quadratic in exactly the spans that
      need dropping.
- [x] 4.5 Record the number of dropped entries on the INFO log line and in the
      `compaction` event payload, so a summary built from a partial span is
      identifiable afterwards. The count of truncated events is recorded
      alongside it, for the same reason.
- [x] 4.6 Orchestrator unit tests: an oversized payload is truncated with the
      marker and a board-sized payload is not; the assembled request never exceeds
      the ceiling; the drop count is reported.

## 5. (B) Make the auto-compaction trigger measure the whole request

**Not implemented — the owner withheld sign-off on (B), and it remains a live
option.** The tasks are kept as written so the work can start without
re-deriving the analysis. The proposed requirement text is in `design.md` under
"Proposed spec text for (B)", outside this change's spec delta on purpose.

- [ ] 5.1 Hoist `render_prompt_with_inline_skills` from `prompt_run.py:224-228` to
      above the auto-compaction call, leaving the prompt event emission and the
      `skill_loaded` announcements at `:230-233` where they are so transcript
      ordering does not change.
- [ ] 5.2 Pass the fixed-cost estimate — system prompt, tool definitions via
      `estimate_tokens_for_tools` (`runtime/tokens.py:79-83`), and the rendered
      user message — into `maybe_auto_compact`, which adds the replay estimate and
      compares the sum against the window.
- [ ] 5.3 Add the guard the design requires: skip compaction when the total
      reaches the threshold but the replay is too small for a summary to be
      smaller than it, using the session's mean `CompactionRecord.tokens_used` or
      a fixed floor on the first compaction. Log the skip once per job, naming
      fixed request cost as the cause.
- [ ] 5.4 Extend the INFO log line at `prompt_run.py:868-874` to report the
      component estimates, not just the ratio. This is the only practical way to
      observe agreement with the context widget on a real session.
- [ ] 5.5 Leave `CONTEXT_COMPACTION_THRESHOLD` at `0.8`. Correcting the
      measurement and moving the threshold are separate decisions and must not be
      bundled.
- [ ] 5.6 Do not build the message list twice. The replay reconstruction is the
      expensive part; the fixed-cost-plus-replay sum is the same number without a
      second `list_completed_jobs_for_replay`.
- [ ] 5.7 Orchestrator unit tests: the trigger includes system prompt, tools and
      the rendered user message; a mentioned skill's content raises the estimate;
      a session whose fixed cost alone exceeds the threshold makes no summarizing
      call and logs the skip; trigger and metadata endpoint agree on the shared
      components for one session.
- [ ] 5.8 Move the proposed requirement text from `design.md` into a spec delta at
      that point, and correct the stale context-window wording in the existing
      "Auto-compaction at job start" requirement while rewriting it.

## 6. (C) Say what the replay limits will drop

- [x] 6.1 Add one line of helper text under each of the two limit fields in
      `services/dashboard/features/play/components/play-config-panel.tsx:250-266`:
      the message limit counts conversational messages and never the compaction
      summary; the tool-exchange limit keeps the newest board-state result and
      discards older ones. `TextInputField` gained the optional `description` prop
      its sibling `TextareaField` already had, so nothing about the existing
      fields' appearance changed.
- [x] 6.2 Dashboard unit test asserting both helper texts render, so the wording
      cannot silently drift away from
      `runtime/session_transcript.py:390-421`.

## 7. Close out

- [x] 7.1 Run `./scripts/lint.sh --fix`, `./scripts/test.sh unit`, and
      `./scripts/test.sh integration` against a started infrastructure stack.
      Lint clean; unit suites green with agent-orchestrator at 480 (from 470) and
      dashboard at 602 in 74 files (from 598 in 73); agent-orchestrator
      integration green against the running infrastructure.
- [x] 7.2 Drive the change in the running app through the browser: a long session
      that auto-compacts, the widget's ratio compared against the logged ratio for
      the same moment, and a forced compaction failure showing the turn completing
      with a `compaction_failed` event. Done as far as the environment allows.
      (C) was verified in a browser: a dev server built from this branch, run on a
      free port against the deployment's own orchestrator, shows both helper lines
      under their fields in the session config drawer, and the throwaway session
      it needed was deleted afterwards. The two orchestrator-side observations
      could not be made: the deployment runs another branch's image, and
      provoking a real auto-compaction needs a session that crosses 0.8 of the
      window, which none in the deployment has. Both are covered by tests that
      drive the worker end to end instead. The comparison of the widget's ratio
      against the logged ratio belongs to (B), which was not built.
- [x] 7.3 Remove the two unused imports ruff reports in `compaction.py:8,12`
      (`build_message_history`, `estimate_tokens_for_messages`) — 4.4 gives the
      second one a use, and the first is simply dead. `build_message_history`
      removed; `estimate_tokens_for_messages` is now used by 4.4. `ruff check` on
      `compaction.py` is clean. Adding `ruff check` to the Python arm of
      `scripts/lint.sh`, which today runs only `black`
      (`scripts/lint.sh:13,21`), is a repo-wide change and belongs to its own
      issue.
- [x] 7.4 Update the spec delta in this change to match what was actually built,
      and grep the change for placeholder markers before considering it done. The
      delta now covers (A) only. Archiving is left to the owner, since (B) is
      still open on this change.
- [ ] 7.5 Record on DRA-12 which gates were approved, what was left unbuilt, and
      the outcome of 3.5 and 4.3 — both are measurements whose results outlive
      this change. 4.3's numbers are recorded above and in the proposal; 3.5 is
      still open. The Linear comment is the owner's to post from this change's
      report.
