# One question, one card: stop the event stream delivering a row twice

## Why

DRA-34 reports, with a screenshot, that the same `ask_user` question is visible
twice in the Play transcript. The screenshot shows three renderings of one
question: a collapsed generic `ask_user` tool card reprinting the question text
and `choices: [4 items]`, and then **two identical "Question for you" cards**.

The literal duplicate is a server defect, not a rendering one, and it was
established over the wire before anything changed. A pending question was seeded
into the orchestrator's Postgres exactly as `ask_user` records it, and the same
payload was pushed onto its Valkey live-event stream exactly as the handler
publishes it. `GET /jobs/{id}/events/stream?after=0` then answered:

```
$ curl -sN ".../jobs/8d30e3fc.../events/stream?after=0"
id: 3448
event: tool_call
id: 3449
event: user_question
event: user_question        ← no id line at all
```

Decoding the frames shows one payload arriving as two events:

```
tool_call      -> id: '3448'
user_question  -> id: '3449'                 (Postgres job_events.id)
user_question  -> id: '1785342527756-0'      (Valkey stream entry id)
```

The dashboard then rendered two cards, confirmed in the browser: two
`user-question-card` nodes, both showing the same wording.

**The mechanism.** `JobEventStreamService.stream` has two sources for the same
event. It polls `Repository.list_events` for durable rows *and* it forwards the
live event bus — and almost every publish in the orchestrator is preceded by an
`append_event`, so most live events are a second copy of a row the same stream
also yields from Postgres. That is deliberate: the bus exists so an event reaches
the browser without waiting for the next poll.

What was missing is that the two copies must be *identifiable as one event*. The
dashboard de-duplicates on `JobEventResponse.id` (`upsertStreamEvent` in
`features/play/lib/play-session-events.ts`), and the live copy carried the bus's
own id — a Valkey stream entry id, or an in-memory counter — which identifies the
delivery rather than the event. So the client could not tell the two apart, and
`aggregateEvents` emitted two `user_question` rows.

**This was never specific to questions.** The same double delivery applied to
every event both persisted and published: `failure`, `completion`,
`skill_loaded`, `subagent_started`, `subagent_failed`, `compaction_failed`,
`user_question_answered`, `user_question_closed`, and `cancellation`. Two things
had been hiding it:

- `aggregateEvents` already carried a targeted workaround — it keeps only the
  last `failure` per job, with the comment *"so the UI doesn't show duplicate
  error cards"*. That is this bug, patched once at the symptom for one event
  type.
- Streaming `model_output` and `reasoning` chunks already solve it properly, in
  the shape this change generalises: a chunk carries `snapshot_event_id`, the
  persisted row's id, and the client keys on that instead of the bus id.
  `user_question` simply never got the equivalent.

The remaining event types got away with it because of how they aggregate rather
than because they were correct: a duplicate `completion` overwrites the same
model-output buffer, and duplicate `subagent_started` events collapse in a map
keyed by child job id. `skill_loaded` and `cancellation` did visibly duplicate.

**The two other renderings are a presentation problem, and the user asked for the
look to be improved as well.** `ask_user` is a builtin tool, so the orchestrator
records a `tool_call` and a `tool_result` for it like any other, and DRA-22's
renderer registry turned that pair into a generic card whose collapsed header
serialises the arguments — which for `ask_user` *is* the question text. And the
choices themselves rendered as borderless ghost buttons in a wrapping row, so
four choices with descriptions read as static text, broke across three ragged
lines, and pushed the longest description off the card edge.

## What Changes

### A live event carries the id of the durable row it copies

`LiveJobEvent` gains a `durable_event_id`, and `LiveEventBus.publish` gains a
keyword argument for it. Both bus implementations carry it: the in-memory bus on
the dataclass, the Valkey bus as a stream field alongside `event_type`,
`payload_json` and `created_at`. It is deliberately **not** put inside
`payload_json`, which is forwarded to the browser verbatim — this is stream
plumbing, not event data.

`serialize_live_event` then prefers it over the bus's own id, so both copies of
one event reach the client under one id and the existing de-duplication collapses
them. A live frame also gains its `id:` SSE line, which it previously omitted, so
it is identified like every other frame.

No client change is required, and the mechanism matches the `snapshot_event_id`
one already in place for streaming chunks.

### Every publish that has a durable twin passes that twin's id

All thirteen append-then-publish pairs are converted, across
`runtime/prompt_run.py`, `runtime/builtin_tools.py`, `runtime/worker.py` and
`api/routers/jobs.py`. `append_event` already returned the row id, so each pair
captures it and hands it to the publish.

Two publishes are deliberately left without one, and say so in a comment:

- The streaming `reasoning` and `model_output` chunks. A chunk is not a copy of a
  finished row but a growing prefix of one the client must keep replacing in
  place, which is what `snapshot_event_id` is for.
- `compaction`. Its summary's durable home is the separate compaction job created
  alongside it, not a `job_events` row on the job being compacted, so nothing in
  that job's event list will ever repeat it.

### Two cancellation publishes are removed rather than converted

`mark_job_cancelled` appends the `cancellation` event itself, inside the
repository, which has no event bus to hand an id to. Both callers in
`prompt_run.py` published a second copy of that row, which is what made one
cancellation render twice. The publishes are removed: the stream's own poll —
200 ms by default — delivers the durable row on a path that is terminating
anyway.

The `missing_model_config` failure additionally persisted a *narrower* payload
(`{"code": ...}`) than it published. Now that the two copies share an id and
therefore collapse, they must agree, so the durable row carries the full failure.
That also fixes a smaller pre-existing defect: a reload previously showed less
about that failure than the live stream had.

### An `ask_user` exchange no longer also renders as a tool card

`ask_user` is added to `TOOL_PRESENTATIONS`, and its renderer returns nothing:
the `user_question` row is that exchange's representation, and it shows the
wording, the choices and the answer better than a serialised argument list does.

An **errored** exchange keeps the generic card. A failed `ask_user` — arguments
that did not validate, a call from a subagent, a cancelled or missing question —
writes no `user_question` event at all, so that card is the only place the
failure is visible. Suppressing it unconditionally would have hidden a whole
class of failure, which is why the rule is conditional rather than a blanket
exclusion.

This also establishes that a registry renderer may return nothing, recorded in
`services/dashboard/AGENTS.md` next to the registry it describes.

### The choices are laid out as readable option rows

Inside the OpenUI Lang component library, `ChoiceList` becomes a vertical stack
and each `Choice` becomes a full-width bordered row with the label above its
description. A row has a hover and an active state so it reads as a target, and a
disabled row goes flat and faded and stops responding to the pointer. The
description wraps instead of being clipped at the card edge.

The choice is a hand-rolled `button` rather than a Hero UI one, which is what
`services/dashboard/AGENTS.md` already prescribes for the transcript: it is
deliberately plain `div`/`button` plus theme tokens, and a full-width two-line
option row is not any Hero UI `Button` variant. The free-text row's Send button
stays Hero UI, as it is elsewhere.

None of this moves the security boundary. A `Choice` still takes an integer index
and nothing else, its label, description and submitted value are still read from
the stored question rather than from the program, every renderer still re-checks
its own props, and every model-authored string is still a plain React text child.

### The regression is pinned at both ends

- `tests/unit/test_job_event_stream.py` asserts that a durable row and its live
  copy reach the client under one id, and that a publish with no durable twin
  keeps the bus id. Reverting `serialize_live_event` fails the first with
  `{'1000000000', '2'} == {'2'}` — the two ids the bug produced.
- `tests/unit/test_builtin_tools_ask_user.py` asserts the `ask_user` handler
  publishes the question under the id of the row it just appended. Reverting that
  one publish fails it.
- `features/play/__tests__/play-transcript-tool-calls.test.tsx` asserts an
  answered and a pending `ask_user` render no tool card and that the question
  wording appears nowhere, while an errored one still renders the generic card
  with its error chip.
- `features/play/__tests__/user-question-openui.test.tsx` keeps its eleven
  existing security assertions and gains the layout ones.

## Non-goals

- **Removing the live event bus, or making it a wake-up signal only.** Dropping
  the live payload would have been a smaller change, but `compaction` has no
  durable twin on the job it is published against, so it would have been lost.
- **Unifying `durable_event_id` with `snapshot_event_id`.** They answer different
  questions — one marks a copy of a finished row, the other a growing prefix of
  an unfinished one — and the client's chunk handling also strips `stream` from
  the payload so an unchanged chunk re-renders nothing. Collapsing them would
  risk that for no gain.
- **Removing the `failure` de-duplication in `aggregateEvents`.** It also guards
  a genuine case: a retried job records a failure per attempt, and only the last
  is the outcome.
- **The `compaction` summary appearing both on the job being compacted and as its
  own compaction job block.** That is a separate question about where a summary
  belongs, not a duplicate delivery of one event, and it is left alone.
- Changing `ask_user`'s arguments, its validation, its timeout behaviour, or the
  server-side answer check, which remains the real boundary.
- Changing any other tool's card, or any part of the transcript outside the
  question surface.
- Adding authentication to the event stream, or changing its reconnect cursor
  contract.

## Impact

- Affected specs: `agent-orchestrator` (a live event and the durable row it
  copies are one event to a client; the question timeline requirement gains that
  constraint), `dashboard` (the renderer registry may suppress a card whose
  exchange another row represents; the question surface's choice layout).
- Affected code:
  - `services/agent-orchestrator/src/agent_orchestrator/runtime/live_events.py` —
    `LiveJobEvent.durable_event_id`, the `publish` signature on the protocol and
    both implementations, and the Valkey subscriber reading the field back.
  - `services/agent-orchestrator/src/agent_orchestrator/runtime/job_event_stream.py`
    — `serialize_live_event` preferring the durable id, and the live frame
    carrying an `id:` line.
  - `services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py`,
    `runtime/builtin_tools.py`, `runtime/worker.py`,
    `api/routers/jobs.py` — every append-then-publish pair passing the durable
    id; the two cancellation publishes removed; the `missing_model_config`
    failure persisting the payload it publishes.
  - `services/agent-orchestrator/src/agent_orchestrator/runtime/compaction.py` —
    a comment recording why this publish has no durable twin.
  - `services/dashboard/features/play/lib/tool-call-presentation.ts` and
    `features/play/components/tool-exchange-block.tsx` — the `ask_user`
    presentation, its renderer, and the widened renderer return type.
  - `services/dashboard/features/play/lib/user-question-library.tsx` — the option
    row and the vertical choice stack.
  - Tests: `tests/unit/test_job_event_stream.py`,
    `tests/unit/test_builtin_tools_ask_user.py`,
    `features/play/__tests__/play-transcript-tool-calls.test.tsx`,
    `features/play/__tests__/tool-call-presentation.test.ts`,
    `features/play/__tests__/user-question-openui.test.tsx`.
- Documentation, kept current in the same change: `services/dashboard/AGENTS.md`
  gains the rule that a registry renderer may return nothing and when that is
  legitimate.
- No database migration. The Valkey stream gains one optional field, and the
  subscriber treats it as absent on entries written before this change, so a
  stream in flight across a deploy is read without error. No dependency change,
  no Dockerfile change, no new environment variable, and no service added or
  removed, so `docker-compose.yaml`, `.env.example`, `scripts/` and the
  `Makefile` need no edit.
- Behaviour a user notices: one question renders as one card; a cancellation and
  a loaded skill each render once; an `ask_user` call no longer prints its
  question above the card that asks it; and the choices are legible option rows
  that do not overflow. A cancellation reaches the browser up to one poll
  interval later than before.
