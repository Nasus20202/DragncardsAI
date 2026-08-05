# Tasks

Numbering follows DRA-12's `tasks.md` section 5 where the work is the same, so
the two can be read against each other.

## 1. Establish the divergence as a number before changing anything

- [x] 1.1 Read the archived DRA-12 change — `proposal.md` for the reasoning,
      `design.md` for "(B) Make the trigger measure the request it protects" and
      its "Proposed spec text for (B)", `tasks.md` items 5.1-5.8 — and treat the
      recorded "smaller-is-better is not the shared principle" decision as
      binding.
- [x] 1.2 Read both measurement sites: `maybe_auto_compact`
      (`runtime/prompt_run.py`) and `build_context_metadata`
      (`runtime/session_transcript.py`). The first estimated
      `build_message_history` only; the second estimated system prompt + replay
      + MCP tools.
- [x] 1.3 Measure the gap on real sessions through the running deployment's own
      `GET /sessions/{id}/context`. Result: a constant 12,779 tokens (system
      prompt 1,588 + MCP tools 11,191) on every session, 9.98% of the
      128,000-token window; the full table is in `proposal.md`.
- [x] 1.4 Measure the components neither side counted: built-in tool
      definitions (1,071 tokens for a top-level job, 205 for a subagent) and the
      rendered user message (bare prompt 4 tokens; the largest four skills
      inlined at `MAX_INLINE_SKILLS = 4` render to 16,301).
- [x] 1.5 Write the failing test first and record its failure against the base
      commit: `test_auto_compact_counts_the_whole_request_not_only_the_replay`
      failed with `assert 0 == 1` on `86101f8`.

## 2. Put the number in one place

- [x] 2.1 Add `runtime/context_estimate.py` with `ContextEstimate` and
      `estimate_request` — the only function that adds context components
      together.
- [x] 2.2 Extract `builtin_tools_as_openai` in `runtime/builtin_tools.py` so
      the registry and the estimate render built-in definitions through one
      function rather than two copies of the same shape.
- [x] 2.3 Add `resolve_session_request_tools` to `api/tool_catalog.py`,
      returning the OpenAI-shaped list a top-level job would send — built-in and
      MCP, persona-narrowed — on top of the existing
      `list_effective_session_tools`.

## 3. Make the widget's side measure the request

- [x] 3.1 `build_context_metadata` delegates its arithmetic to
      `estimate_request` and takes `request_tools` from the caller.
- [x] 3.2 Build the system prompt with `personas=` so the persona catalogue is
      counted, as the worker always counts it.
- [x] 3.3 Thread `request_tools` through `repositories/context.py` and resolve
      it in `api/routers/context.py`, which gains the live event bus dependency
      that building the built-in definitions needs.
- [x] 3.4 Leave the response shape and the dashboard untouched: three breakdown
      fields, no new row, no restyling.

## 4. Make the trigger measure the request (DRA-12 items 5.1-5.6)

- [x] 4.1 (5.1) Hoist `render_prompt_with_inline_skills` above the
      auto-compaction call, leaving the prompt event and the `skill_loaded`
      announcements where they were so transcript ordering does not change.
- [x] 4.2 (5.2) Pass the system prompt, the tool list and the rendered user
      message into `maybe_auto_compact`, which adds the replay and compares the
      sum against the window through `estimate_request`.
- [x] 4.3 (5.3) Add the fixed-cost guard, comparing the replay against the
      measured token length of the session's most recent summary, falling back
      to `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS`. Log the skip once per job,
      naming fixed request cost as the cause. This departs from DRA-12's
      "mean `CompactionRecord.tokens_used`"; the reason is in `design.md`.
- [x] 4.4 (5.4) Extend the INFO log line to report the component estimates, not
      just the ratio.
- [x] 4.5 (5.5) Leave `CONTEXT_COMPACTION_THRESHOLD` at `0.8`.
- [x] 4.6 (5.6) Do not build the message list twice for the estimate — the
      caller's components are passed in rather than rebuilt. The replay itself
      is built once for the estimate and once for the request, because
      compaction rewrites it in between; DRA-12's item was about not
      reconstructing it a second time *to measure it*, which this does not do.
- [x] 4.7 Add `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS` to `config.py` with a
      validator and the reasoning for its default recorded beside it.
- [x] 4.8 Remove the now-dead `WorkerService._maybe_auto_compact` wrapper,
      which had no callers and a signature that no longer matched.

## 5. Tests (DRA-12 item 5.7)

- [x] 5.1 `test_context_estimate.py`: the estimator counts all four components;
      `fixed_cost` is everything but the replay; the replay alone understates
      the request; the ratio is clamped and rounded for transport; a zero window
      does not divide by zero; the breakdown omits the user message; an inlined
      skill raises the estimate.
- [x] 5.2 `test_auto_compact_counts_the_whole_request_not_only_the_replay`: a
      request the replay alone would not have triggered now compacts. Asserts
      its own precondition, so it cannot pass for the wrong reason.
- [x] 5.3 `test_fixed_request_cost_alone_does_not_call_the_summarizer`: a
      session over the threshold on fixed cost with a small replay makes no
      summarizing call and logs the skip exactly once, naming fixed cost.
- [x] 5.4 `test_trigger_and_context_endpoint_report_the_same_components`: runs a
      job through the worker, reads the trigger's structured `context_estimate`
      log field and asserts the three shared components equal the endpoint's
      breakdown, and that the endpoint's total is the trigger's less the user
      message.
- [x] 5.4a `test_the_guard_still_holds_after_a_session_has_compacted_once`: the
      carried-forward summary in the replay does not count as compactable
      history. Written after the security review found the first version of the
      guard compared the whole replay and was therefore unreachable once a
      session had compacted; the test fails against that version.
- [x] 5.5 Update the tests that set `CONTEXT_COMPACTION_THRESHOLD=0.0` to set
      `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS=0` explicitly, so they still
      exercise the trigger rather than the new guard, with the reason in a
      comment.
- [x] 5.6 Rewrite `context_api_test_support.py` so the expected components are
      assembled from primitives rather than from the functions under test. The
      formula duplicated in those helpers was the same class of duplication that
      let the two sides drift, but replacing it with a call to the production
      resolver would have made the tools assertion unable to fail at all.

## 5b. Corrections made in response to review

- [x] 5b.1 Count the restored conversation context on both sides. It is
      caller-supplied, unbounded, prepended to every request and never
      compacted, and neither side counted it. Excluded again from the guard's
      compactable span.
- [x] 5b.2 Name the seat inbox as the one component the estimate cannot
      include, in the spec delta and in `design.md`, because collecting it
      delivers the messages it reads.
- [x] 5b.3 Add the second arm of the guard: skip when the unshrinkable parts
      reach the context window on their own, where no summary can produce a
      request that fits. Log which arm fired.
- [x] 5b.4 Correct the code comment and the README, which described the guard as
      preventing repeated compaction it does not in fact prevent.
- [x] 5b.5 Pass `session_orchestrated` and `seat_identity` into
      `build_preview_builtin_tools`, closing a measured 457-token understatement
      for orchestrated sessions and 309 for seat sessions — and fixing
      `GET /sessions/{id}/tools` in the same place, which was wrong for the same
      reason.
- [x] 5b.6 Make `maybe_auto_compact`'s three new arguments required, so a caller
      that forgets one fails loudly instead of silently reverting to measuring
      less than the request.
- [x] 5b.7 Log the components as a structured `context_estimate` field as well
      as in the message, and read the structured field in the parity test, so a
      correctness test is not coupled to log wording.
- [x] 5b.8 Rebuild the expected tool list in `context_api_test_support.py` from
      primitives instead of calling the function under test, which had made the
      tools assertion unable to fail.
- [x] 5b.9 Correct the docstring claiming the replay is reconstructed once per
      turn: it is built for the estimate and again for the request, because
      compaction rewrites it in between.
- [x] 5b.10 Make `estimate_request` treat an empty system prompt as zero, as it
      already treated an empty user message.

## 6. Housekeeping this change owns

- [x] 6.1 Remove the two dead `F401` imports in
      `runtime/session_transcript.py` (`AgentSession`, `CompactionRecord`) and
      the three in `tests/unit/test_auto_compaction.py` (`AsyncMock`,
      `ToolCall`, and an unused `as mock_compact` binding). `runtime/compaction.py`
      itself is clean — `ruff check --select F` reports nothing there; the
      brief's two `F401`s are the pair in `session_transcript.py`, the other
      file on this measurement path.
- [x] 6.2 Do not add `ruff check` to `scripts/lint.sh`. It is why these
      survived, and it is its own issue with its own blast radius (10 findings
      in agent-orchestrator, 14 in game-service on this base).
- [x] 6.3 Document `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS` in the
      agent-orchestrator README's configuration table alongside the other
      context settings.

## 7. Verification

- [x] 7.1 `./scripts/lint.sh --fix` clean.
- [x] 7.2 `./scripts/test.sh unit`: game-service 384, agent-orchestrator 612
      (599 baseline + 13 new), history-service 193, eval-service 291, dashboard
      631 in 76 files, shared 38.
- [x] 7.3 `./scripts/test.sh integration agent-orchestrator`: 29 passed,
      matching the baseline.
- [x] 7.4 `pnpm typecheck` in `services/dashboard`: clean.
- [x] 7.5 `openspec validate --all`: 17 passed, 1 failed — the failure is the
      pre-existing `spec/typed-game-actions`, which also fails on the base.
- [x] 7.6 Confirm or refute DRA-34's suspected duplicate compaction summary.
      Confirmed and explained in `design.md`; not fixed, since it is out of
      scope for this change.
- [x] 7.7 Cross-check the new estimator read-only against the deployment's own
      Postgres, with no app and no worker. System-prompt and replay figures came
      out identical to the live endpoint's on all eight sessions; the tools
      figure differs only because the in-cluster MCP URL is unreachable from the
      host. Recorded in `design.md`.
- [x] 7.8 Confirm through the running dashboard (Playwright) that the context
      widget is a pure renderer of the endpoint's number, which is what lets
      this change be server-side only: session `dbe97e1b` displayed
      "69.3k / 128.0k tokens (54%)" against the endpoint's `tokens_used=69278`,
      `usage_ratio=0.5412`. The stack runs the base build, so this establishes
      the rendering relationship, not the corrected figure.
- [x] 7.9 Record what could not be exercised: no provider on this stack reports
      `available=true`, so no real agent run reaches the threshold. The trigger
      was driven through the real worker path with constructed inputs instead,
      and the limits are stated in `design.md`.

## 8. Follow-ups this change deliberately does not take

- [ ] 8.1 Revise `CONTEXT_COMPACTION_MIN_REPLAY_TOKENS` from measured summary
      sizes once any session has produced a `CompactionRecord`. The trigger's
      log line reports both the replay and the floor it was compared against,
      which is the data this needs.
- [ ] 8.2 DRA-12 task 3.5 — compact one long session both ways and diff the
      summaries for dropped tracked state. Still blocked on a working provider
      and a long game, as it was on DRA-12.
- [ ] 8.3 Decide whether `CONTEXT_COMPACTION_THRESHOLD` should move now that the
      number is honest. Deliberately separate, per DRA-12 and the issue.
- [ ] 8.4 The duplicate compaction summary in a live transcript (7.6). Belongs
      with DRA-34.
