# Tasks

Nothing here is done. DRA-12 is a proposal-only change: the deliverable is a
document the owner approves or rejects, and no runtime behaviour was altered while
writing it. This list is the implementation that would follow **if** it is
approved, written so the work can start without re-deriving the analysis.

Two approval gates, because the two halves carry different risk:

- **Gate 1 — section (A)**: bounds an unbounded LLM request and stops a
  compaction failure from failing the user's turn. Fixes a fault; changes nothing
  about a healthy turn. Sections 2-4 below.
- **Gate 2 — section (B)**: changes *when* history is summarised, so it changes
  what the model sees on some turns. Needs the owner's explicit sign-off,
  separately from Gate 1. Sections 5-6 below.

Section 1 is verification of the baseline and is worth doing under either gate.
Section 7 closes out whichever gates were opened.

## 1. Re-confirm the baseline before changing it

- [ ] 1.1 Confirm `perform_compaction` still passes `after_job_id=None` and so
      re-reads every job from session start
      (`services/agent-orchestrator/src/agent_orchestrator/runtime/compaction.py:120-124`).
- [ ] 1.2 Confirm `maybe_auto_compact` is still awaited unguarded inside the job's
      `try` (`runtime/prompt_run.py:206-207`, handlers at `:567`/`:578`), so a
      compaction exception marks the job failed.
- [ ] 1.3 Confirm the trigger still estimates the replay only
      (`prompt_run.py:857-860`) while the metadata endpoint estimates system
      prompt + replay + tools (`runtime/session_transcript.py:160-186`).
- [ ] 1.4 Confirm inlined skill content still lives only in the model's copy of
      the user message and never in the stored prompt
      (`runtime/skills.py:195-232`, `prompt_run.py:220-229`), so replay is
      unaffected by DRA-15.
- [ ] 1.5 Reproduce the defect end-to-end rather than trusting the reading: drive
      a session long enough to auto-compact, with the compaction call forced to
      exceed the window, and record that the user's turn fails. This is the
      evidence the whole change rests on and it must exist before the fix.

## 2. (A4) Stop a compaction failure from failing the turn — ship this first

- [ ] 2.1 Wrap the `maybe_auto_compact` call at `prompt_run.py:206-207` so no
      exception from it escapes into the job's failure handlers.
- [ ] 2.2 Treat `perform_compaction`'s two `ValueError` cases — "No completed jobs
      to compact" (`compaction.py:111`) and "No history content to compact"
      (`:163`) — as no-ops that log at info and emit nothing.
- [ ] 2.3 Emit a `compaction_failed` job event for a real failure, carrying the
      failure message and the usage ratio that triggered the attempt.
- [ ] 2.4 Add `compaction_failed` to `STREAM_EVENT_TYPES`
      (`services/dashboard/features/play/lib/play-session-events.ts:63-79`) and
      render it in the transcript alongside the existing `compaction` block
      (`features/play/components/play-transcript.tsx:140-150,266`). No migration:
      `job_events.event_type` is a free string.
- [ ] 2.5 Update `services/agent-orchestrator/AGENTS.md`'s event-type list, which
      enumerates every job event type.
- [ ] 2.6 Orchestrator unit tests: a failing summarizing call leaves the job
      completed and emits `compaction_failed`; a session with no completed job
      emits nothing and completes; the manual endpoint still returns an error for
      the same failure.
- [ ] 2.7 Dashboard unit test: the transcript renders a `compaction_failed` event,
      and the event type is present in `STREAM_EVENT_TYPES`.

## 3. (A1) Checkpoint the compaction input

- [ ] 3.1 Pass `after_job_id=existing_compaction.covers_up_to_job_id` in
      `perform_compaction` when a previous record exists, matching what
      `build_message_history` already does
      (`runtime/session_transcript.py:88-93`). Keep the previous summary in the
      request — it is what makes the checkpoint safe.
- [ ] 3.2 Add a "from session start" mode to `POST /sessions/{session_id}/compact`
      that ignores the checkpoint, so a user can rebuild a summary they believe
      lost information. Automatic compaction always uses the checkpointed form.
- [ ] 3.3 Expose that mode in the dashboard only if it is free to do so; a
      request body flag with no UI is acceptable for a recovery path. Do not add a
      second button to the context widget for it.
- [ ] 3.4 Orchestrator unit tests: a second compaction's input contains the
      previous summary and only post-checkpoint jobs; the from-start mode contains
      every eligible job; the first compaction of a session is unchanged.
- [ ] 3.5 Measure the drift risk the design names as its one open question:
      compact the same long session under both modes and diff the summaries for
      dropped tracked state (hero HP, threat, villain phase, cards in play).
      Record the result on DRA-12 whichever way it comes out — a checkpointed
      summary that loses state is a reason to revisit, and a clean diff is the
      evidence that closes the question.

## 4. (A2, A3) Bound the compaction input's size

- [ ] 4.1 Add a per-event character budget applied separately to a tool call's
      arguments text and a tool result's content text in
      `compaction.py:141-171`, appending an explicit `… [truncated, N chars
      omitted]` marker where text is cut.
- [ ] 4.2 Add the budget as a setting alongside the existing context settings in
      `config.py:121-130`, with a default of 20 000 characters and a validator
      requiring it to be positive.
- [ ] 4.3 Validate that default against a real game before merging: instrument the
      character length of `arguments` and `result` per tool across one full
      session and confirm the budget sits above the 99th percentile of
      `get_game_state`. A board state must never be truncated. If it does not,
      move the default, not the mechanism.
- [ ] 4.4 Estimate the assembled summarization request with
      `estimate_tokens_for_messages` — already imported and unused at
      `compaction.py:12` — and drop history entries oldest-first while it exceeds
      `window × CONTEXT_COMPACTION_THRESHOLD`.
- [ ] 4.5 Record the number of dropped entries on the INFO log line and in the
      `compaction` event payload, so a summary built from a partial span is
      identifiable afterwards.
- [ ] 4.6 Orchestrator unit tests: an oversized payload is truncated with the
      marker and a board-sized payload is not; the assembled request never exceeds
      the ceiling; the drop count is reported.

## 5. (B) Make the auto-compaction trigger measure the whole request

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

## 6. (C) Say what the replay limits will drop

- [ ] 6.1 Add one line of helper text under each of the two limit fields in
      `services/dashboard/features/play/components/play-config-panel.tsx:250-266`:
      the message limit counts conversational messages and never the compaction
      summary; the tool-exchange limit keeps the newest board-state result and
      discards older ones.
- [ ] 6.2 Dashboard unit test asserting both helper texts render, so the wording
      cannot silently drift away from
      `runtime/session_transcript.py:390-421`.

## 7. Close out

- [ ] 7.1 Run `./scripts/lint.sh --fix`, `./scripts/test.sh unit`, and
      `./scripts/test.sh integration` against a started infrastructure stack.
- [ ] 7.2 Drive the change in the running app through the browser: a long session
      that auto-compacts, the widget's ratio compared against the logged ratio for
      the same moment, and a forced compaction failure showing the turn completing
      with a `compaction_failed` event.
- [ ] 7.3 Remove the two unused imports ruff reports in `compaction.py:8,12`
      (`build_message_history`, `estimate_tokens_for_messages`) — 4.4 gives the
      second one a use, and the first is simply dead. Consider adding `ruff check`
      to the Python arm of `scripts/lint.sh`, which today runs only `black`
      (`scripts/lint.sh:13,21`) and is why these went unreported; that is a
      repo-wide change and belongs to its own issue if it turns up other findings.
- [ ] 7.4 Update the spec delta in this change to match what was actually built,
      then archive, and grep the archived change and
      `openspec/specs/agent-orchestrator/spec.md` for placeholder markers before
      considering it done.
- [ ] 7.5 Record on DRA-12 which gates were approved, what was left unbuilt, and
      the outcome of 3.5 and 4.3 — both are measurements whose results outlive
      this change.
