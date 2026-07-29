## 1. Establish the mechanism before changing anything

- [x] 1.1 Read the three changes that built this surface — DRA-5 (`ask_user`, the
      three durable event types, the question card), DRA-29 (the OpenUI Lang
      rendering) and DRA-22 (the tool-call renderer registry) — and list the
      candidate causes rather than assuming one.
- [x] 1.2 Rule the candidates in or out against the code:
      a React key collision (ruled out — rows are index-keyed over the aggregated
      list, so a duplicated row means a duplicated event, not a key clash);
      the model calling `ask_user` twice (ruled out — one `job_questions` row and
      one `tool_call`);
      the orchestrator emitting two `user_question` events (ruled out — one
      `append_event` in `make_ask_user_handler`);
      a deliberate second surface such as a composer banner (ruled out — the only
      renderer of a question is `UserQuestionCard`, reached from one `AggEvent`
      kind);
      the same event delivered twice under different ids (**confirmed**).
- [x] 1.3 Confirm the delivery path: `JobEventStreamService.stream` yields from
      `Repository.list_events` *and* forwards the live bus, `ask_user` both appends
      and publishes, and the bus assigns its own id (a Valkey stream entry id, or
      an `InMemoryLiveEventBus` counter) which `serialize_live_event` passed
      through.
- [x] 1.4 Confirm the client cannot recover: `upsertStreamEvent` keys on
      `JobEventResponse.id`, and its only other path is gated on
      `payload.stream === true` with a `snapshot_event_id`, which a
      `user_question` has neither of.
- [x] 1.5 Note that the streaming chunks already solve this correctly via
      `snapshot_event_id`, and that `aggregateEvents` already carries a
      symptom-level workaround for `failure` ("so the UI doesn't show duplicate
      error cards") — both evidence that the defect is general, not question-specific.
- [x] 1.6 Audit every `publish` call site and classify it: paired with an
      `append_event` (thirteen), a streaming chunk using `snapshot_event_id` (two),
      a publish of a row the repository appends (two cancellations), or a publish
      with no durable twin at all (`compaction`).

## 2. Reproduce it, over the wire and in the browser

- [x] 2.1 Seed one pending question into the owner's running orchestrator Postgres
      exactly as `ask_user` records it — `agent_sessions`, `session_model_configs`,
      a running `jobs` row, a pending `job_questions` row, and the `tool_call` and
      `user_question` events — rather than spending model budget provoking one.
- [x] 2.2 Push the same `user_question` payload onto the job's Valkey live-event
      stream with `XADD`, as the handler's `publish` does, so both sources carry it.
- [x] 2.3 Read `GET /jobs/{id}/events/stream?after=0` and record the frames: one
      `tool_call`, then `user_question` twice — the second with no `id:` line.
- [x] 2.4 Decode the frames and record the two ids for the one payload: `'3449'`
      (Postgres) and `'1785342527756-0'` (Valkey). This is the defect, stated
      exactly.
- [x] 2.5 Open the seeded session in the dashboard and confirm two
      `user-question-card` nodes with identical question text, guarding the
      evaluation with a URL check because the browser is shared.
- [x] 2.6 Capture the before screenshot and confirm it matches the report: a
      collapsed generic `ask_user` card above two identical question cards, with a
      long choice description clipped at the card edge.

## 3. Make a live event and the row it copies one event

- [x] 3.1 Add `durable_event_id` to `LiveJobEvent`, documenting on the field why it
      exists and what rendered twice without it.
- [x] 3.2 Add a keyword-only `durable_event_id` to `LiveEventBus.publish` on the
      protocol and on both implementations.
- [x] 3.3 Carry it through the Valkey bus as its own stream field beside
      `event_type`, `payload_json` and `created_at` — deliberately not inside
      `payload_json`, which is forwarded to the browser verbatim.
- [x] 3.4 Read it back in `ValkeyLiveEventSubscriber.get`, treating it as absent on
      entries written before the field existed so a stream in flight across a
      deploy is read without error.
- [x] 3.5 Prefer it over the bus id in `serialize_live_event`, and record in that
      docstring why the stream has two sources for one event and why the id must be
      the durable one.
- [x] 3.6 Give the live SSE frame its `id:` line, which it previously omitted, so
      it is identified like every other frame.

## 4. Pass the durable id from every publish that has a twin

- [x] 4.1 `builtin_tools.py`: `user_question`, `user_question_closed`,
      `skill_loaded`, the subagent outcome event, `subagent_started`, and
      `subagent_failed`.
- [x] 4.2 `prompt_run.py`: the `missing_model_config` failure, the interrupt
      `completion`, `skill_loaded`, `fail_job`'s failure, `complete_job`'s
      completion, and `compaction_failed`.
- [x] 4.3 `worker.py`: the crash `failure`, keeping the two independent `try`
      blocks and defaulting the id to `None` so a failed append still publishes.
- [x] 4.4 `api/routers/jobs.py`: `user_question_answered`.
- [x] 4.5 Make the `missing_model_config` failure persist the same payload it
      publishes. The two copies now share an id and collapse, so a narrower durable
      payload would mean a reload showed less than the live stream had.
- [x] 4.6 Remove the two `cancellation` publishes in `prompt_run.py` instead of
      converting them: `mark_job_cancelled` appends that event inside the
      repository, which has no bus to hand an id to, and the stream's own 200 ms
      poll delivers the row on a path that is terminating anyway.
- [x] 4.7 Comment the two deliberate exemptions where they are: the streaming
      chunks, which use `snapshot_event_id` because they are a growing prefix of an
      unfinished row rather than a copy of a finished one; and `compaction`, whose
      summary lives on a separate compaction job.
- [x] 4.8 Sweep every `publish` call site again and confirm each either passes a
      durable id or is one of the three documented exemptions.

## 5. Stop the transcript reprinting the question as a tool card

- [x] 5.1 Add `ask_user` to `TOOL_PRESENTATIONS` under a `user_question`
      presentation key, widening `ToolPresentation` accordingly.
- [x] 5.2 Add the renderer to `RENDERERS` and widen `ToolExchangeRenderer` to
      return `React.ReactElement | null`. Returning `null` is safe: the transcript
      maps rows into a `space-y-2` container whose `> * + *` rule leaves no gap for
      an absent child.
- [x] 5.3 Render nothing for a successful or still-pending exchange, and keep the
      generic card when `view.status === "error"` — a failed `ask_user` writes no
      `user_question` event, so that card is the only place the failure shows.
- [x] 5.4 Record both halves of the rule in the renderer's comment and in
      `services/dashboard/AGENTS.md` beside the registry: suppress a card only when
      another transcript row is that exchange's representation, and never for its
      error path.

## 6. Make the choices readable

- [x] 6.1 Turn `ChoiceList` from a wrapping row into a vertical stack, and update
      the component's model-facing description to match what it now lays out.
- [x] 6.2 Make each choice a full-width bordered row with the label above its
      description, hand-rolled as a `button` per the transcript's own convention
      rather than a Hero UI `Button` variant.
- [x] 6.3 Give a row hover and active states so it reads as a target, and express
      the unanswerable state with `disabled:` utilities so one class string covers
      flat, faded and pointer-inert.
- [x] 6.4 Make the description wrap rather than clip, so it can no longer run off
      the card edge, keeping only a generous clamp as a bound against a
      pathological length.
- [x] 6.5 Make the free-text row full width and wrap-safe so it lines up with the
      option rows above it.
- [x] 6.6 Confirm nothing in the security model moved: `Choice` still takes an
      integer index only, label/description/value still come from the stored
      question via `QuestionContext`, every renderer still re-checks its props, and
      every model-authored string is still a plain React text child.
- [x] 6.7 Keep every `data-testid` unchanged, since other suites key on them.

## 7. Pin the regression at both ends

- [x] 7.1 Assert in `tests/unit/test_job_event_stream.py` that a durable row and
      its live copy reach the client under one id.
- [x] 7.2 Assert there that a publish with no durable twin still keeps the bus id,
      so the `compaction` case is not broken by the fix.
- [x] 7.3 Update the existing stream test that asserted a live frame carries no
      `id:` line, which was pinning the old behaviour.
- [x] 7.4 Assert in `tests/unit/test_builtin_tools_ask_user.py` that the handler
      publishes the question under the id of the row it just appended.
- [x] 7.5 Prove the tests fail before the fix: reverting `serialize_live_event`
      fails 7.1 with `{'1000000000', '2'} == {'2'}`, and reverting the `ask_user`
      publish fails 7.4. Restore both afterwards.
- [x] 7.6 Assert in `features/play/__tests__/play-transcript-tool-calls.test.tsx`
      that an answered and a pending `ask_user` render no tool card and that the
      question wording appears nowhere, and that an errored one still renders the
      generic card with its error chip.
- [x] 7.7 Assert the registry entry in
      `features/play/__tests__/tool-call-presentation.test.ts`.
- [x] 7.8 Add layout assertions to
      `features/play/__tests__/user-question-openui.test.tsx` while keeping its
      eleven existing security assertions passing unchanged.

## 8. Verify the fix end to end

- [x] 8.1 Run the fixed orchestrator and dashboard on free high ports against the
      running infrastructure, without touching the owner's containers or running
      any `docker` command.
- [x] 8.2 Re-read the SSE stream for the same seeded question and confirm both
      `user_question` frames now carry the durable id.
- [x] 8.3 Open the seeded session in the browser and confirm exactly one
      `user-question-card`, again guarding the evaluation with a URL check.
- [x] 8.4 Confirm the generic `ask_user` tool card is gone and the question wording
      appears once.
- [x] 8.5 Capture the after screenshot and confirm the option rows are bordered,
      stacked, and that the long description wraps inside the card.
- [x] 8.6 Delete the seeded session, job, question and events, and the Valkey
      stream key, leaving the owner's data as it was.
- [x] 8.7 Stop the servers started on the high ports and confirm the ports are
      free, having bound nothing the owner's stack uses.

## 9. Checks

- [x] 9.1 `./scripts/lint.sh --fix` then `./scripts/lint.sh` exits 0.
- [x] 9.2 `./scripts/test.sh unit` — report counts before and after.
- [x] 9.3 `pnpm typecheck` in `services/dashboard`.
- [x] 9.4 `./scripts/test.sh integration agent-orchestrator`.
- [x] 9.5 `openspec validate dra-34-duplicate-questions --strict`.
- [x] 9.6 `openspec validate --all` — exactly one failure, the pre-existing
      `spec/typed-game-actions`.
- [x] 9.7 Grep the change directory for placeholder text (`TBD`, `TODO`, `???`,
      `FIXME`, `XXX`, "to be decided", "update after archive") and confirm none.
