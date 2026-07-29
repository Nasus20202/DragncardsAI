# Better context management for chat sessions

## Why

DRA-12 was split out of DRA-6 ("Improve chat experience"), which asked for
"loading skills in chat (@player ?), better context management etc." The skill
half became DRA-15 and shipped. This half names no defect, so the first job of
this proposal is to establish what the current behaviour actually is, and only
then to judge the four directions the issue speculates about: surfacing the
existing `recentMessageLimit` / `recentToolExchangeLimit` knobs in the chat,
choosing defaults instead of unlimited, summarising older turns, or trimming tool
payloads.

The answer, established in **Current behaviour** below, is that three of those
four are already built, already deliberate, or would make things worse — and that
there is one real defect the issue did not name: **the mechanism that exists to
stop a session from overflowing its context window can itself overflow the
context window, and when it does, the user's turn fails.**

So this proposal recommends changing very little, and changing it in the one
place that is demonstrably wrong rather than in the four places the issue
guessed at.

## Current behaviour

Every claim here is from the code on this branch.

### Replay is unlimited by default; compaction is the only bound that applies

`context_recent_message_limit` and `context_recent_tool_exchange_limit` are
nullable columns with no default value
(`services/agent-orchestrator/src/agent_orchestrator/schema_migrations/sql/0003_replay_windows.postgresql.sql:1,3`).
`SessionCreateRequest` defaults both to `None`
(`services/agent-orchestrator/src/agent_orchestrator/schemas/sessions.py:27-28`),
the dashboard's new-session draft initialises both to `""` and labels the fields
with the placeholder "Unlimited"
(`services/dashboard/features/play/lib/session-draft.ts:138-139`,
`services/dashboard/features/play/components/play-config-panel.tsx:250-266`), and
`_normalize_replay_limit` treats `None` **and** any value `<= 0` as "no limit"
(`services/agent-orchestrator/src/agent_orchestrator/runtime/session_transcript.py:375-378`).

So on a session nobody configured, `build_message_history` replays every prior
job with status `completed`, `interrupted`, or `failed` since the last compaction
checkpoint, in full: each job's prompt, each `model_output`, and each tool call
paired with its complete tool result
(`session_transcript.py:83-144`, `:225-372`;
`services/agent-orchestrator/src/agent_orchestrator/repositories/context.py:125-159`).

The only bound that applies without configuration is compaction. At job start,
when `multi_turn_memory` is enabled, the worker calls `maybe_auto_compact`
(`services/agent-orchestrator/src/agent_orchestrator/runtime/prompt_run.py:206-207`),
which reconstructs the replay, estimates its tokens with `tiktoken`, and compacts
if the ratio against the window reaches `CONTEXT_COMPACTION_THRESHOLD`
(`prompt_run.py:853-866`). The threshold defaults to `0.8` and the window falls
back to `CONTEXT_WINDOW_SIZE` = `128000` when the provider does not report a
model context length
(`services/agent-orchestrator/src/agent_orchestrator/config.py:121-130`,
`prompt_run.py:848-851`).

Compaction summarises the history into a `CompactionRecord`
(`services/agent-orchestrator/src/agent_orchestrator/runtime/compaction.py:194-199`)
and writes a synthetic `job_type = "compaction"` job so the summary is visible in
the transcript (`repositories/context.py:69-109`). That synthetic job is excluded
from replay by `Job.job_type != "compaction"`
(`repositories/context.py:149`), so the summary is not double-counted. Raw
`JobEvent` rows are never deleted.

### The knobs and the context health are already surfaced in the chat

This is the direction the issue names first, and it is largely already done.

`ContextHealthWidget`
(`services/dashboard/features/play/components/context-health-widget.tsx`) is
rendered inside the composer
(`services/dashboard/features/play/components/play-prompt-box.tsx:268-273`). It
shows a usage bar that turns amber at 70% and red at 85%
(`context-health-widget.tsx:38-42`), `tokens_used / context_window_size` with a
percentage, a hover breakdown splitting that into **system prompt / replay /
tools** (`:127-166`), the compaction count, the last-compacted timestamp, a
"Memory off" state when `multi_turn_memory` is false, and a **Compact** button
wired to `POST /sessions/{id}/compact`
(`:88-97`;
`services/dashboard/features/play/lib/use-play-session-actions.ts:350-378`).

The transcript renders each compaction as its own collapsible "Context
compaction" block
(`services/dashboard/features/play/components/play-transcript.tsx:140-150,266`),
and a `compaction` event arriving mid-run refreshes the widget
(`services/dashboard/features/play/lib/use-job-streaming.ts:112`).

The two replay limits themselves are editable in the session config drawer, both
at creation and on an existing session — saving PATCHes them
(`play-config-panel.tsx:250-266`;
`use-play-session-actions.ts:117`, `:190-198`). `multi_turn_memory` is the one
context setting with no dashboard control at all; it defaults to `TRUE`
(`0002_context_management.postgresql.sql:1`) and the widget only reports it.

### The auto-compaction trigger measures less than the request it protects

`maybe_auto_compact` counts **only** the replay (`prompt_run.py:857-860`). The
request the worker then builds contains more than that: the system prompt
(`prompt_run.py:209-211`), any restored conversation context (`:212-214`), the
replay (`:215-219`), and the user message *as rendered* — which since DRA-15
begins with the full `SKILL.md` of every skill the prompt `@`-mentioned
(`:224-229`) — and it is sent alongside `tools`, the built-in registry plus every
MCP tool definition the session resolved (`:204`).

This is not an oversight in one place; the two surfaces deliberately measure
different things and the spec codifies both. `build_context_metadata` — what the
widget shows — counts system prompt + replay + tools
(`session_transcript.py:160-186`), and
`openspec/specs/agent-orchestrator/spec.md:743-747` requires exactly that. The
auto-compaction requirement at
`openspec/specs/agent-orchestrator/spec.md:722-728` requires only the replay
estimate. So the number the user sees in the widget and the number that decides
whether to compact are different numbers for the same session at the same moment,
and the widget's is the closer of the two to reality.

### What DRA-15 added to a single turn, and what it did not add to every turn

`render_prompt_with_inline_skills`
(`services/agent-orchestrator/src/agent_orchestrator/runtime/skills.py:195-232`)
prepends each mentioned skill's `SKILL.md` plus its reference inventory to the
model's copy of the user message. The stored `job.prompt` stays the typed text,
so the transcript shows the typed text and a later turn replays the typed text
(`prompt_run.py:220-223`). **The inlined content costs its tokens on exactly one
turn**, which is the right design and means DRA-15 did not make replay bigger.

It did make one turn materially bigger, and the magnitudes are real: the five
runtime skills in `skills/` are 8.4 KB to 32.3 KB of `SKILL.md` each — roughly
2k to 9k tokens — and `MAX_INLINE_SKILLS` allows four per message
(`skills.py:16`). A mention-heavy turn can therefore add on the order of 10k-30k
tokens to the request. `maybe_auto_compact` runs before the user message is
rendered and never sees any of it.

### State-heavy tool results are already handled specially — but only when a limit is set

`_STATE_HEAVY_GAME_SERVICE_TOOLS` marks six game-service tools whose results
carry a whole board (`session_transcript.py:24-31`), and
`_select_recent_tool_exchange_orders` guarantees the newest state-heavy exchange a
slot in the budget and then fills the rest with the newest non-state-heavy
exchanges (`:390-421`). That logic runs only when
`context_recent_tool_exchange_limit` is set — with the default of unlimited it is
dead code, and every historical `get_game_state` result is replayed verbatim.

Two things bear on how bad that is. Tool results are already the *simplified*
projection, not raw DragnCards state
(`openspec/specs/simplified-game-state/spec.md`), so the payloads are pre-trimmed
at the source. And DRA-5's `ask_user` is a built-in tool
(`services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py:1410,1481`),
so its `assignment` is not `game-service` and
`_is_state_heavy_tool_exchange` returns `False` for it
(`session_transcript.py:487-491`): a user's answer to a direct question is
replayed as an ordinary tool exchange and, once a limit *is* configured, is
droppable like any other. Recent ones survive; an older one is displaced by newer
routine calls.

### The defect: compaction reads the whole session, unbounded, and fails the turn when it overflows

`perform_compaction` calls `list_completed_jobs_for_replay` with
`after_job_id=None` — commented "Get everything (compaction covers it all)"
(`compaction.py:120-124`) — so it re-reads **every** job since session start,
ignoring the previous compaction checkpoint, and then builds one user message
containing every prompt, every `model_output`, and the *complete* `arguments` and
`result` dicts of every tool event, with no limit and no truncation
(`compaction.py:141-171`). The previous summary is supplied as an extra system
message on top of that (`:133-139`). It is sent to the *same* model as the game
agent with the same `gateway_options` and `provider_options` (`:180-187`), so it
also inherits whatever reasoning setting the session runs with.

Three consequences follow, in increasing severity:

1. The summarization request is **strictly larger** than the replay that
   triggered it — the replay had limits and a checkpoint applied; this has
   neither.
2. Its size grows monotonically with total session length, so the second
   compaction costs at least as much as the first and the tenth costs far more.
   Compaction gets more expensive precisely as it becomes more necessary.
3. When it exceeds the window, `perform_compaction` raises. `maybe_auto_compact`
   is awaited unguarded at `prompt_run.py:207`, inside the job's `try`, so the
   catch-all handlers at `prompt_run.py:567` / `:578` mark the **user's turn**
   failed. The mechanism whose entire purpose is to prevent context overflow
   becomes the thing that fails the turn, at exactly the point in a long game
   where the user most needs it to work.

That third point is the only thing in DRA-12's territory that is unambiguously
broken rather than debatable, and it is what makes this issue worth acting on at
all.

### Two smaller inaccuracies found while reading

Neither is worth its own change; both are recorded so the next reader does not
re-derive them.

- The context metadata response reports the **provider-reported model context
  length** when Bifrost supplies one, falling back to `CONTEXT_WINDOW_SIZE`
  (`services/agent-orchestrator/src/agent_orchestrator/api/routers/context.py:27-36`),
  and it carries a seventh field `token_breakdown`
  (`session_transcript.py:197-201`). The spec describes `context_window_size` as
  "configured `CONTEXT_WINDOW_SIZE`" and lists six fields
  (`openspec/specs/agent-orchestrator/spec.md:749-755`). The code is the better
  behaviour; the spec text is stale.
- `compaction.py:8` and `:12` import `build_message_history` and
  `estimate_tokens_for_messages` and use neither; `ruff check` reports both as
  F401. They survive because `scripts/lint.sh` runs only `black` for Python
  (`scripts/lint.sh:13,21`) and never invokes `ruff check`.

## What Changes

Nothing about what the model sees on a turn that already fits inside its context
window. Two changes, both to the compaction machinery, in priority order.

- **(A) Bound and checkpoint the compaction input, and stop a compaction failure
  from failing the user's turn.** Summarise only what has happened since the
  previous `CompactionRecord.covers_up_to_job_id` — the previous summary is
  already supplied as a system message and already carries everything before that
  point — and cap the text each tool event contributes to the summarisation
  transcript, with an explicit marker where text was cut. Wrap the
  auto-compaction call so a failure degrades into a logged, transcript-visible
  event and the turn proceeds on the history it has, instead of failing.
- **(B) Make the auto-compaction trigger measure the request it is protecting.**
  Count system prompt + tool definitions + replay + the current turn's rendered
  user message, which is what the widget already counts plus the turn itself, and
  evaluate the threshold against that. Keep `CONTEXT_COMPACTION_THRESHOLD` at
  `0.8`.
- **(C) Say on the two limit fields what setting them will drop.** The config
  drawer offers two integers with no indication that a tool-exchange limit
  preserves the newest board state and discards older ones. One line of helper
  text each. This is cosmetic and rides along with (B); it is not a reason to
  open a change on its own.

Spec deltas accompany (A) and (B) because both modify existing requirements in
`openspec/specs/agent-orchestrator/spec.md`. (C) needs no delta — the dashboard
spec already requires the fields to exist and does not constrain their labels.

**(B) is the only change that alters when the model's context is compacted, and
it moves compaction earlier. It needs the owner's explicit sign-off, separately
from (A).** (A) can be approved on its own and is worth doing on its own.

## Why not the four directions the issue named

### Surfacing `recentMessageLimit` / `recentToolExchangeLimit` in the chat — rejected

The chat already surfaces context *health*: a bar, a percentage, a three-way
token breakdown, a compaction count, a last-compacted time and a Compact button,
all inside the composer (`context-health-widget.tsx`). The two limits are already
editable in the session drawer, and already editable mid-session. Moving them
into the composer would duplicate a control that exists and would ask the user to
hand-tune two integers whose correct values depend on the model's window, the
size of the resolved tool catalog, and how state-heavy the session has become —
none of which is visible next to the input. What is genuinely missing is not
another input but an explanation of what a limit discards, which is (C).

### Choosing non-unlimited defaults — rejected on evidence, revisit after (B)

This is the direction with the strongest surface appeal and the weakest support.
A default limit takes history away from every session, including the short ones
that fit comfortably, and any number named today would be a guess: the right
message count depends on a window that ranges from tens of thousands to a million
tokens across the enabled providers, and the right tool-exchange count depends on
how many board snapshots a particular game accumulates. Compaction already bounds
the unbounded case, and it bounds it by *summarising* rather than *deleting*,
which preserves strictly more than a hard window does.

The reason to revisit later rather than never: the measurement that would justify
a default does not exist yet, and today's numbers under-report because of the gap
(B) fixes. The honest sequence is (B), then log per-turn replay sizes across a few
real games, then set a default that only bites the sessions that were actually in
trouble. Recorded here as a deliberate deferral with a named precondition, not as
an open question.

### Summarising older turns — rejected as a new mechanism

Compaction *is* summarisation of older turns. Its prompt already demands a state
snapshot, pending decisions, recent activity, and decisions with rationale
(`compaction.py:24-92`). The gap is not that summarisation is missing; it is that
the summariser reads too much, which is (A). A second, rolling per-N-turns
summariser would create a second source of truth for "what happened earlier"
alongside `CompactionRecord`, a second thing that can disagree with the
transcript, and a new failure mode in the middle of a turn — to reach an outcome
(A) reaches by checkpointing the summariser that already exists. Worth revisiting
only if bounded compaction still produces summaries that lose state, and that
would be a question about the compaction *prompt*, not about adding a layer.

### Trimming tool payloads — rejected for replay, adopted for compaction input

Three reasons not to truncate a retained tool result in replay. The payloads are
already the simplified projection rather than raw state
(`openspec/specs/simplified-game-state/spec.md`). The replay path already handles
the expensive case structurally — it keeps the newest board state and drops older
ones once a limit is set (`session_transcript.py:390-421`) — so truncation would
be a second, overlapping mechanism. And a half-truncated board state is worse
than an absent one: the model cannot distinguish "this card is not in play" from
"this card was cut off", and it will act on the difference.

The one place truncation is right is the compaction *input*, where the reader is a
summariser being asked for the gist and a marker saying "cut here" is honest
information rather than a silent lie. That is inside (A).

### Doing nothing at all — seriously considered

Three of the issue's four readings collapse on inspection and the fourth is a
deferral, so "little or nothing should change" was the likely outcome going in,
and would have been the recommendation if the compaction input were bounded. It
is not, and the unguarded `await` at `prompt_run.py:207` turns that into a path
from "this game has gone on a while" to "the user's turn failed". That is worth
fixing, and it is the kind of fault that only appears in long sessions — which is
the situation DRA-6 was complaining about.

### One option outside the issue's list, named so it is not mistaken for an oversight

Compaction currently runs on the session's own game model with the session's own
reasoning settings (`compaction.py:180-187`). Summarising with a cheaper or
smaller model is a reasonable idea and is **not** proposed here: it is a cost and
provider decision rather than a context-management one, and this change is
deliberately not making new provider decisions.

## How this sits against DRA-10 and DRA-15

**DRA-10** widened what the *judge* sees — round-scoped context including the
actions that follow a move — on the explicit ruling that accuracy outranks
payload size. This proposal does not contradict that ruling, and does not treat
smaller-as-better as self-evident. The two consumers differ in three ways that
change the right answer:

| | Judge (DRA-10) | Chat agent (DRA-12) |
| --- | --- | --- |
| Context growth | Bounded by one round; does not accumulate | Cumulative — every turn carries the last |
| Behaviour at the ceiling | No ceiling reached in practice | Hard ceiling; over it the request errors |
| Failure mode | A wrong number on a dashboard | The user's turn fails, mid-game |

The shared principle both changes obey is not "smaller" and not "bigger": *a
consumer must be given the whole of what it is being asked to reason about, and
the mechanism that enforces the ceiling must be honest about where the ceiling
is.* (B) makes the ceiling honest; (A) stops the safety valve from breaking.
Neither removes history from a turn that fits. What this proposal explicitly does
**not** do is trim what the agent sees while it still fits — that would be the
chat-side version of the thing DRA-10 rejected.

**DRA-15** matters to the baseline in two opposite ways, and both are already
accounted for above. It did *not* make replay heavier — inlined skill content
lives only in the model's copy of one user message and never enters the stored
prompt a later turn replays (`skills.py:195-232`, `prompt_run.py:220-223`). It
*did* make one turn heavier by up to tens of thousands of tokens, and that turn's
weight is invisible to the auto-compaction trigger, which runs before the message
is rendered. (B) is the change that makes DRA-15's cost visible to the mechanism
that is supposed to react to it; it is the main reason (B) is worth doing at all
rather than filed as tidiness.

## Impact

- `services/agent-orchestrator` — `runtime/compaction.py` (checkpointed input,
  bounded per-event text), `runtime/prompt_run.py` (trigger inputs, guarded
  auto-compaction call), `runtime/tokens.py` or a small helper for the shared
  estimate, plus unit tests.
- `services/dashboard` — helper text on the two limit fields in
  `features/play/components/play-config-panel.tsx`; a `compaction_failed` event
  type would also need adding to `STREAM_EVENT_TYPES`, because the browser
  registers one named `EventSource` listener per type and silently drops anything
  absent from that list (`services/agent-orchestrator/AGENTS.md:44-46`).
- `openspec/specs/agent-orchestrator/spec.md` — the "Auto-compaction at job
  start" and "Manual compaction endpoint" requirements, and the stale
  `context_window_size` / field-count wording in "Context metadata endpoint".
- No migration. No new state, in memory or otherwise; the checkpoint (A) needs is
  the `covers_up_to_job_id` column that `compaction_records` already has
  (`0002_context_management.postgresql.sql:5-12`).
- Nothing in this change alters the judge, the history service, or the eval
  service.
