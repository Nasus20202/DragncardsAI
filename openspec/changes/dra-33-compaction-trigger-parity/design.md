# Design — one source for the context number

DRA-12's `design.md` already contains the design for this change, under
"(B) Make the trigger measure the request it protects". This document does not
repeat it. It records three things: where the implementation follows that
design, the two places it deliberately departs from it and why, and what the
change could not establish.

The binding decision from DRA-12 still holds and nothing here contradicts it:

> **smaller-is-better is not the shared principle.** The judge's context and
> the chat agent's differ because one is round-bounded and non-cumulative while
> the other is cumulative against a hard ceiling. Nothing removes history from
> a turn that fits.

This change removes nothing from any turn. It changes only the arithmetic that
decides whether to enter the compaction path, and what the endpoint behind the
widget reports.

## The choice the issue left open: which measure wins

The trigger measured the replay; the widget measured the system prompt, the
replay and the MCP tools. Neither measured the request. Three options existed:
the trigger adopts the widget's measure, the widget adopts the trigger's, or
both move to a third.

**Both move to a third, and it is the request the worker actually sends.** The
widget's measure was the closer of the two but still wrong — it omitted the
built-in tool definitions the model is offered and the persona catalogue the
worker always builds into the system prompt. Adopting it wholesale would have
produced two numbers that agreed with each other and with nothing else. The
trigger's measure was strictly worse and adopting it would have made the widget
under-report by the same 12,779 tokens the trigger did.

The measure is therefore: **system prompt + every tool definition offered +
replay + any restored conversation + the current turn's user message as
rendered**. The first four are shared. The last is the trigger's alone, and
deliberately so — see below.

### The two components found by review, and what happened to each

**Restored conversation context is counted.** `POST /sessions/restore` writes a
caller-supplied conversation into the session's `metadata_json`, and
`prompt_run` prepends it to *every* request the session ever sends. It is
unbounded, compaction never rewrites it, and neither side was counting it —
precisely the class of uncounted fixed cost this change exists to remove, on
the session type created for resuming long games. It now counts on both sides,
inside the replay component (it is replayed prior messages, just ones that
arrived by restore) so the widget needs no new row, and it is excluded again
from what the guard treats as compactable.

**The seat inbox is not counted, and cannot be.** `_collect_seat_inbox` is not
a read: it marks the inter-seat messages it returns as delivered, and they must
be delivered exactly once, on the turn that carries them. Measuring it would
mean either delivering messages on a turn that might not send them or building a
second non-consuming read path. It is bounded by the pending messages and open
findings for one seat, which is far smaller than the components above. The spec
delta names it as an explicit exclusion rather than leaving it implied.

## Where the single number lives

`services/agent-orchestrator/src/agent_orchestrator/runtime/context_estimate.py`.

`estimate_request(system_prompt, tools, replay_messages, user_message,
context_window_size) -> ContextEstimate` is the only function in the service
that adds context components together. `ContextEstimate` owns `total`,
`fixed_cost`, `usage_ratio` and the endpoint's breakdown, so no caller does its
own arithmetic on the parts.

Two callers:

- `PromptRunService.maybe_auto_compact` passes the components the worker has
  already built — the system prompt from `prompt_run.py`, the tool list it will
  send, the replay, and the rendered user message.
- `SessionTranscriptService.build_context_metadata` passes the system prompt it
  builds for the session, the tool list resolved by
  `resolve_session_request_tools`, and the replay. It passes no user message.

The components themselves are still assembled twice — the worker builds a real
`BuiltinToolRegistry` because it dispatches through it, while the endpoint uses
the existing `build_preview_builtin_tools` path. That is the one remaining
place the two sides could drift, and it is why
`test_trigger_and_context_endpoint_report_the_same_components` exists: it runs
a real job through the worker, parses the trigger's own log line, and asserts
the three shared components equal the endpoint's breakdown for the same session
with no job in between. A divergence in assembly turns that test red.

## Why the user message is not shared, and is not a defect

The endpoint reports a session at rest. There is no current turn when a user is
merely looking at the widget, and the existing spec is explicit that the
estimate "SHALL NOT include ... a future user prompt that has not yet been
submitted". So `estimate_request` is given no user message there and the
breakdown has no field for it — an always-zero row would be noise on a widget
this change is not allowed to restyle.

This leaves one real, deliberate difference: on a turn that inlines four
skills, the trigger's total is up to 16,301 tokens above the widget's. That is
not the two measures disagreeing about the same thing; it is the widget
describing a session and the trigger describing a request. The trigger reports
the component on its INFO line, so the difference is observable rather than
hidden, and DRA-12's spec text already scoped the agreement scenario to "the
same replay, system prompt, and tool-definition contributions".

## Departure 1: the guard measures the previous summary, not `tokens_used`

DRA-12's design specified the fixed-cost guard as "the running mean of
`CompactionRecord.tokens_used` for the session, or a fixed floor on the first
compaction". The implementation uses the measured token length of the most
recent summary's text instead, with the floor unchanged in role.

The reason is that `CompactionRecord.tokens_used` is not the summary's size.
`perform_compaction` sets it from `extract_tokens_from_response`
(`runtime/compaction.py`), which reads the OpenAI-compatible `usage.total_tokens`
— the summarizing call's **prompt plus completion**. It therefore includes the
whole span that was summarized and grows with it. Using it as the expected
summary size would compare the replay against a number that already contains a
replay, and would suppress compaction hardest on exactly the long spans that
need it. `count_tokens_for_text(record.summary_text)` is the thing being asked
for, and it is exact.

(That `tokens_used` means the call's total rather than the summary's length is
pre-existing and is not changed here. It is a reasonable meaning for a cost
field; it is simply the wrong input for this guard.)

## The guard compares the compactable span, not the whole replay

The first implementation of the guard compared `estimate.replay` against the
floor, and the security review caught that this makes the guard **unreachable**
for any session that has compacted once. `build_message_history` prepends the
previous summary as a system message and the replay-window limits never drop
it, so the replay always contains at least that summary — and the floor, after
the first compaction, *is* that summary's size. The comparison was therefore
always false, and a session over the threshold on fixed cost would have bought
a blocking summarizing call, a `CompactionRecord` row and a synthetic
compaction job on every turn, forever. That is worse than the behaviour this
change set out to fix.

The guard now compares the **compactable span** — the replay less the
carried-forward summary — which is what compaction would actually replace. A
regression test pins it: a session with a checkpoint and nothing new since is
required to skip and to say so. Against the pre-fix code that test fails, with
the log showing the trigger going straight past the guard into
`NothingToCompactError`.

The suggestion of skipping whenever `fixed_cost / window` reaches the threshold
was not taken. It would refuse to compact a session that has both a large fixed
cost *and* a large history, where compaction still reduces the request even
though it cannot get it under the threshold. What *was* taken is the exact form
of that idea: skip when `fixed_cost >= context_window_size`, where no summary
can produce a request that fits and the summarizing call is spent before an
inevitable provider refusal. So the guard now has two arms — too little history
to be worth summarizing, and a request that cannot fit however much is
summarized — and the log line names which one fired.

The case deliberately left uncovered, so that neither the code comment nor the
README overclaims: a session whose fixed cost alone is over the *threshold* but
still inside the window, with real history behind it, compacts on every turn.
Each of those compactions genuinely shrinks the request; none of them gets the
ratio back under the threshold. That is a session whose tool catalogue, system
prompt or model is the actual problem, and the trigger's log line is what says
so.

## Departure 2: the floor is stated as a floor, not defended as a measurement

`CONTEXT_COMPACTION_MIN_REPLAY_TOKENS` defaults to `4000`. DRA-12's (A2)
character budget was chosen from 147 real `get_game_state` payloads. No such
data exists here: no session in the deployment has ever compacted, so there is
no real summary to measure. The honest position is written into `config.py`
next to the constant — the floor is a stand-in that applies only until a
session has produced one summary, after which the measured summary size takes
over and the floor stops mattering for that session. 4,000 tokens is about 3%
of the default window and about one mid-sized inlined `SKILL.md`. It is chosen
to be revised from the first real summaries, and the trigger's log line reports
both the replay and the floor it was compared against, which is what makes that
revision cheap.

## Alternatives considered and rejected

**Assemble the full message list, measure it, then compact and rebuild.**
Rejected for the reason DRA-12 gave: it builds the replay twice on every turn,
and `list_completed_jobs_for_replay` loading every prior job with its events is
the expensive part. The component sum is the same number without the second
reconstruction.

**Give the endpoint the built-in tools by having the worker's registry
constructed there too.** `build_builtin_registry` needs a job, a live event bus
and a repository because its definitions carry bound handlers. The existing
`build_preview_builtin_tools` already solves this for
`GET /sessions/{id}/tools` with a synthetic top-level job, so the endpoint
reuses it rather than inventing a second answer.

**Leave the preview's seat and orchestrated-mode gating alone.** This was the
original decision, and review overturned it with a measurement:
`build_preview_builtin_tools` never passed `session_orchestrated` or
`seat_identity`, so an orchestrating session's built-in catalogue was
understated by `report_illegal_action` and `resolve_illegal_action` — **457 of
1,071 tokens, 43%** — and a seat's by `send_player_message` and
`list_my_illegal_actions`, 309 tokens. The orchestrating session is a normal
top-level session with a context widget on the project's primary use case, so
the spec's unconditional parity requirement would have been false there on day
one. The two gating arguments are now passed, from `list_effective_session_tools`,
which fixes `GET /sessions/{id}/tools` at the same time — the endpoint was
understating the same tools for the same reason.

**Model a subagent's request on the endpoint side.** The endpoint reports what a
**top-level** job on the session would send: `resolve_session_request_tools`
passes `is_master_job=True`, and the system prompt is built with
`build_system_prompt` rather than `build_subagent_system_prompt`. A child
session's own widget therefore reports a larger figure than its jobs actually
send — a subagent is offered two built-in tools (205 tokens) rather than five
(1,071), and gets a persona prompt instead of the full catalogue. The error is
in the conservative direction, whether a session is a child is a property of
its jobs rather than of the session row, and the parity requirement is scoped to
top-level jobs. Left as it is, and named here so it is not mistaken for a bug.

**Add a `user_message` row to the widget's breakdown.** Rejected: it would
always read zero there, and the dashboard is the visual reference.

**Lower `CONTEXT_COMPACTION_THRESHOLD` now that the number is honest.**
Rejected as a separate decision, per DRA-12 and the issue. Correcting the
measurement already moves the effective trigger about 13,850 tokens of replay
earlier on this deployment.

## Interaction with DRA-42, restated so it is not assumed away

DRA-42 made live-event publishing best-effort, and `compaction` is the one
event with **no durable twin**: its summary's durable home is the synthetic
compaction job created by `create_compaction_job`, not a `job_events` row on
the job being compacted. This change does not touch that, and does not add any
new reporting that depends on the event arriving. The fixed-cost skip is a log
line, not an event — a skip is the absence of work, and manufacturing a
transcript element for it would put a row on every turn of a session whose tool
catalogue is too large.

## The suspected duplicate summary: confirmed, and left alone

DRA-34 recorded an unresolved observation that the compaction summary appears
both on the job being compacted and as its own compaction job block. It was
cheap to confirm from the code while working here, and it is real, with a
precise cause:

- `play-session-events.ts` pushes a `compaction` transcript item from the
  `compaction` **stream event**, which `perform_compaction` publishes on the
  job being compacted.
- It pushes another from any `model_output` event on a job with
  `job_type = "compaction"`, which is the synthetic job
  `create_compaction_job` writes.
- `use-job-streaming.ts` refreshes on the `compaction` event, which is what
  brings the synthetic job into view in the same moment.

So the duplicate is **live-session-only**. After a reload the stream event is
gone — it has no durable twin — and only the compaction job's block remains.
That also means the two symptoms DRA-34 and DRA-42 describe are the same
mechanism seen from opposite ends: a dropped publish loses the summary from the
running transcript, and a delivered one shows it twice. Fixing it is out of
scope here and is not attempted; the finding is recorded so whoever picks it up
does not have to re-derive it.

## Cross-check against the deployment's own data

The new code was run read-only against the running orchestrator's Postgres —
`Repository` plus `resolve_session_request_tools` plus `get_context_metadata`,
no app, no worker, nothing claimed — over the same eight sessions the proposal
tabulates. The system-prompt and replay figures came out **identical to the
live endpoint's**, to the token, on every session (1,588 system prompt;
replays of 0 / 5,403 / 6,008 / 9,279 / 12,258 / 43,617 / 56,499 / 152,014). So
the refactor changed the arithmetic's *home* without changing what it computes
for those two components.

The tools component in that run reads 1,071 rather than 12,262 because a
process on the host cannot reach `http://game-service:4001/mcp`, the in-cluster
URL the MCP registry row holds, and `list_session_tools` is called with
`ignore_failures=True`. So that run measured the built-in half alone — which is
itself the confirmation that the built-in definitions are now counted and were
worth 1,071 tokens. The corrected figure for each session is therefore the
live endpoint's current total plus 1,071: `dbe97e1b`, for instance, moves from
69,278 (0.541) to 70,349 (0.550) on the widget, while its trigger moves from
56,499 (0.441) to the same 70,349 plus whatever the turn's user message costs.

## What this change did not establish

- **No end-to-end run against a real model.** Every LLM provider on this stack
  reports `available=false` with zero models, so no agent can be driven long
  enough to cross the threshold. The trigger was exercised with constructed
  inputs through the real worker path — `WorkerService._run_job` with a fake
  Bifrost client — which covers the decision, the guard, the log line and the
  compaction call. It does not cover a real provider accepting or rejecting the
  resulting request.
- **The live deployment still runs the old code.** The divergence table in the
  proposal was taken from the running orchestrator's own
  `GET /sessions/{id}/context`, which is the *base* behaviour; the built-in tool
  and inlined-skill figures were measured locally against the same skill roots
  and registry the deployment uses. Confirming the corrected numbers in the
  running stack needs a rebuild, which this change does not perform.
- **DRA-12 task 3.5 (summary drift) remains unmeasured**, for the same reason it
  was left open there: it needs two real summarizing calls over one long game.
  It is a validation of (A1)'s checkpoint, not of this change's arithmetic, and
  nothing here makes it any harder to do later.
