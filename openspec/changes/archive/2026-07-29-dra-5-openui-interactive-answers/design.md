# Design: a question the run waits on

## The one real constraint

A job in this service cannot suspend. `PromptRunService.run` is a bounded `for`
loop over tool rounds holding `messages` as a local list that is never persisted,
and the job status vocabulary (`queued`, `running`, `completed`, `failed`,
`cancelled`, `interrupted`) has no `waiting` member and no re-entry point that
could rebuild a half-finished round. Adding suspend-and-resume would mean
persisting the message history and rewriting the loop as a resumable state
machine — far more than DRA-5 asks for.

The service already has an idiom for "a tool that waits for something external":
`wait_for_subagent`, whose `resolve_child_outcome` blocks *inside the handler*,
polling the durable Postgres row while consuming live events for responsiveness,
under an absolute deadline. `ask_user` follows it. The worker is not stalled by
this: `WorkerService.run_forever` claims a job and immediately detaches it as an
`asyncio` task, so the claim loop keeps running while one job's handler awaits.

The consequence to accept honestly: a question consumes one of the run's tool
rounds and real wall-clock time, and it dies if the worker is stopped. Both are
handled below rather than hidden.

## State machine

A `job_questions` row has exactly three states:

```
                  answer endpoint (choice validated)
   pending ───────────────────────────────────────────► answered   (terminal)
      │
      │  wait deadline expires, or the job's cancellation flag is set
      └───────────────────────────────────────────────► closed     (terminal)
```

`pending → answered` and `pending → closed` are the only transitions, and both are
performed as a single conditional `UPDATE … WHERE id = ? AND status = 'pending'`.
The row count that statement reports is the decision: 1 means this caller won the
transition, 0 means somebody already took it. That is what makes the
double-answer case a database fact rather than a read-then-write race between two
HTTP requests landing on two replicas.

## Where the state lives, and why there

**Postgres, in `job_questions`.** Three requirements force it:

1. The worker asks and an HTTP request answers. They are different processes and
   may be different replicas, so an in-process dict cannot see both — and the
   service guide forbids instance-variable state outright.
2. The choices are the *validation authority*. Checking a submitted answer against
   what the model actually offered means re-reading the offered list from storage,
   not trusting the browser to echo it back.
3. It must survive a reload and a reconnect. Valkey is wrong for the store: the
   live event stream there is capped and expires after 300 seconds, which is
   shorter than a person takes to answer.

Valkey still carries the *notification* — the `user_question` event goes onto the
live bus so the browser sees the question immediately — but it is never the
authority. This mirrors `resolve_child_outcome`'s stance: events make the fast
path fast, the row decides.

Note the deliberate absence of a `GET /jobs/{id}/questions` endpoint. All three
events are appended to `job_events`, which is durable, and the dashboard already
replays a job's events from `after=0` on reconnect. So the answered and closed
states come back on a reload for free, and the dashboard holds no pending-question
state of its own — it derives every question's state from the event list it
already has.

## The four awkward cases, decided

**The user ignores the question.** The wait is bounded by
`ask_user_timeout_seconds` (default 600, following `subagent_wait_timeout_seconds`)
measured as an *absolute* deadline. On expiry the handler transitions the row
`pending → closed` with reason `timeout`, appends and publishes
`user_question_closed`, and returns a non-error tool result saying nobody answered
and telling the model to proceed on its own best judgement or report that it is
blocked — the same "here is what happened, act on it" shape
`describe_child_outcome` uses for an abandoned wait. Closing the row *before*
returning is what stops a late click from being accepted for a question nobody is
listening to any more. It is not an error result, because an unanswered question
is a normal outcome and marking it `is_error` invites the model to retry the tool
immediately.

**The user answers twice.** The first `UPDATE … WHERE status = 'pending'` wins.
The second gets 0 rows and the endpoint returns **409** with a human-readable
detail. The model therefore sees exactly one answer, ever. The dashboard also
disables its controls while a submit is in flight, but that is a courtesy: the
double-click defence is the conditional update, because two browser tabs are not
prevented by one tab's disabled button.

**The user reloads mid-question.** Nothing is lost, because nothing was in the
browser. The question, its answer, and its closure are all rows in `job_events`;
the reconnecting dashboard replays them from `after=0` and re-derives the state.
A still-pending question comes back with live buttons and the waiting handler
never noticed. An already-answered one comes back showing the answer, with no
buttons — which is also the honest rendering, since answering again is impossible.

**The session or job ends while a question is pending.** Three distinct paths:
- *Job cancelled.* The handler's poll checks `get_job_cancellation_requested`,
  closes the row with reason `cancelled`, publishes `user_question_closed`, and
  returns; the run then unwinds through the existing cancellation path.
- *Session deleted.* `job_questions.session_id` and `job_id` both cascade on
  delete, so the question goes with it and the answer endpoint answers 404.
- *Worker died — the one case with no active closer.* The row stays `pending`
  because nothing is alive to close it. The answer endpoint therefore refuses on a
  second condition as well as the row's own status: **if the job has reached a
  terminal status, the answer is rejected with 409.** No reaper job is needed —
  the check is at the only place that matters, and the dashboard reaches the same
  conclusion from the job status it already displays, so the buttons go inert.

## Validating a model-authored question, and a user-authored answer

Both directions are untrusted, in different ways.

*From the model*, at tool-call time: the question must be a non-empty string; there
must be between 1 and 8 choices; every choice needs a non-empty `label` and
`value`; values must be unique (otherwise an answer is ambiguous); and question,
label, value, and description are length-capped. A violation returns an error tool
result naming the problem so the model can correct itself, and writes no row —
malformed input from the model is a normal event, not a failure of the run.

*From the browser*, at answer time: exactly one of `choice_value` or `text` is
accepted. A `choice_value` must appear in the `choices` read back from the row, and
`text` is accepted only when the row records `allow_free_text`. Anything else is a
400. This is the "never let a submitted answer widen what the model asked for"
rule, and it is enforced against stored state rather than against anything the
request carries.

*At render time*: choice labels, values, and descriptions are model-authored
strings that become UI. They are rendered as React text children only — never
through `ReactMarkdown`, never `dangerouslySetInnerHTML`, and never interpolated
into an attribute or anything executable. This is why the tool takes a structured
choice list instead of a UI description: the model picks the words, the dashboard
picks the markup, and the boundary between them is a typed contract rather than a
rendering engine. It is also precisely the boundary that makes the OpenUI question
answerable later without touching anything but the component.
