# A persona for the main chat, and an allowlist of the subagents it may spawn

## Why

DRA-38 asks for two things a persona can currently not do:

> Now we can choose a persona only for the spawned subagents. We should be able to:
>
> - select one for the "main" chat
> - select a list of allowed subagents to use (like for skills)

Both gaps are real and both are one-sided in the same way.

**A persona describes an agent, and the one agent a user actually talks to cannot
be given one.** DRA-16 made a persona a bundle of a system prompt, a skill
selection, and a tool allowlist, and made it reachable from exactly two places: a
`spawn_subagent` argument and a session's `default_subagent_persona`. DRA-30 added
a third, the per-seat persona of an orchestrated game. Every one of those
configures a *child*. The session's own agent — the one holding the conversation,
spending the context window, and calling the tools — has no persona field at all.
Someone who wants their main chat agent to behave a particular way has to write
that into every prompt, because the mechanism built for exactly this purpose is
not wired to it.

**Every session may spawn every persona that exists anywhere in the deployment.**
`agent_personas` is deployment-global by design: a persona exists to outlive one
session. The consequence nobody chose is that a persona written for one game is
nameable by the agent of every other session, and a master job's system prompt
lists the entire catalogue as an invitation. There is no way to say "this session
delegates to the rules checker and to nothing else", and no way to withdraw a
persona from a session that is already running. The issue's own comparison — *"like
for skills"* — points at the fix: a session already selects its skills from a
global registry through `session_enabled_skills`, and personas should be selected
the same way.

These are one change rather than two because they are the same object seen from
both ends. The session persona is *what this agent is*; the allowlist is *what
this agent may make*. They share the persona catalogue, the capture rule, the
storage shape, and — for the allowlist — the enforcement point that decides
whether either is worth anything.

## What Changes

### The session's own agent can be a persona

`agent_sessions` gains a `session_persona` column, accepted on `POST /sessions`
and `PATCH /sessions/{id}` and reported on every session response. When set, the
persona is **resolved and snapshotted at that moment** into the `agent_persona`
key of the session's metadata — the same key, the same snapshot reader, and the
same rule a spawned child already follows. A persona edited or deleted afterwards
does not change a session that already adopted it, exactly as it does not change
a subagent already started from it.

At run time the snapshot contributes two things and no more:

- its system prompt, as the same `## Persona` section a subagent gets, placed
  after the base rules which it cannot override; and
- its `allowed_tools`, narrowing the session's own tool surface through the
  existing filter.

It deliberately does **not** apply the persona's provider, model, gateway options
or skills. Those have their own controls on that same session, written by the same
settings panel, and a persona silently overwriting the rows those controls write
would make the visible pickers misreport what the agent runs with. A spawned child
has no competing control, which is why a child materialises the whole persona and
a session does not. The snapshot records only the fields that are applied, so it
cannot suggest otherwise.

The snapshot is server-owned even though it lives in the client-writable metadata
blob: a client changes the persona by **name**, and `PATCH /sessions` carrying a
`metadata` body can neither forge the snapshot nor drop it.

### A session selects which personas it may spawn

A new `session_allowed_subagents` table records, per session, which personas that
session's agent may start a subagent from. It is shaped like
`session_enabled_skills` — one row per (session, persona), a soft `enabled`
toggle, a foreign key onto the global catalogue — and is managed both atomically
(`allowed_subagents` on `POST /sessions` and `PATCH /sessions/{id}`) and one entry
at a time (`POST`/`GET`/`PATCH`/`DELETE` under `/sessions/{id}/subagents`),
mirroring the session skill endpoints.

**An empty allowlist means no persona may be spawned.** It is never read as "all
personas". Spawning a subagent with *no* persona — which copies the session's own
configuration — is unaffected and remains available to every session, so the
closed default costs a session nothing it had before personas existed.

So that no caller has to interpret an empty array, `GET /sessions/{id}/subagents`
returns **every** persona in the catalogue with its own `allowed` flag rather than
returning only the permitted names, and the empty-means-none rule is stated in the
OpenAPI description of every field that carries the list — which is also the text
of the generated MCP tool.

### The allowlist is enforced at dispatch

The check sits in `_resolve_spawn_persona`, above the persona lookup, which is the
single point every spawn's persona resolution passes through. It therefore covers
a model naming a persona, a session's `default_subagent_persona` falling through
to one, and a scripted HTTP or MCP client driving a prompt — and it refuses before
any child session, child job, or event row is written. The refusal names the
permitted set so the model can correct itself rather than retry.

Filtering the master job's persona catalogue to the allowlist is done too, but it
is presentation: a model can name a persona the catalogue never mentioned, and the
dispatch check is what makes the control real.

Two consistency rules stop the configuration contradicting itself, both `400`:
`default_subagent_persona` must be on the allowlist, and revoking a persona that
is still the default is refused unless the same request clears the default. Both
are validated against the state the request *produces*, before either field is
written, so a rejected combination leaves the session untouched.

### Neither setting is frozen after the first job

`session_mode` is frozen at the first job because an orchestrated session's seats
own persistent sessions recorded against it. Nothing is keyed to the session
persona or to the allowlist, so changing either orphans nothing. For the allowlist
the argument is stronger than symmetry: a control that cannot be revoked once a
game is under way is not a control. The capture rule is what keeps this safe for
the persona — turns already taken keep the snapshot they ran under.

### The dashboard shows both, and shows which state the allowlist is in

The session settings panel gains a **Session persona** picker (the existing
persona picker, reused with its own label and no allowlist narrowing, because what
the session's own agent runs as is a separate choice from what it may delegate to)
and an **Allowed subagents** toggle list built like the skill toggle list above it.

The allowlist section always states, in words, which state it is in: "No personas
allowed" when nothing is ticked, and "N of M personas allowed" otherwise. That
line is the point of the control's design — an unticked list could equally read as
"unrestricted", and a security-shaped control that silently means "everything" is
worse than no control.

The default-subagent picker is narrowed to the allowlist, and un-ticking the
persona that is the current default clears the default with it, so the panel
cannot produce the configuration the orchestrator refuses.

## Capabilities

### Modified Capabilities

- `agent-orchestrator` — the session's own persona and its capture rule, the
  per-session subagent allowlist, its enforcement at spawn dispatch, and the
  consistency rules between the allowlist and the session default.
- `dashboard` — the session persona picker, the allowed-subagents control and its
  explicit empty-state statement, and the narrowing of the default-subagent
  picker.

## Impact

- **Database** — migration `0013_session_persona_and_subagent_allowlist` adds
  `agent_sessions.session_persona` and the `session_allowed_subagents` table in
  both dialects, and backfills the allowlist of every session that existed when it
  ran with the whole persona catalogue so nothing already in flight loses a
  capability.
- **agent-orchestrator** — `storage/models.py`, `repositories/base.py`,
  `repositories/sessions.py`, `repositories/personas.py`,
  `runtime/personas.py`, `runtime/system_prompts.py`, `runtime/prompt_run.py`,
  `runtime/builtin_tools.py`, `schemas/sessions.py`, `api/serializers.py`,
  `api/routers/sessions.py`.
- **dashboard** — `features/shared/lib/types.ts`,
  `features/play/lib/client-api.ts`, `features/play/lib/session-draft.ts`,
  `features/play/lib/last-used-draft.ts`,
  `features/play/lib/use-play-session-actions.ts`,
  `features/play/components/play-config-panel.tsx`,
  `features/personas/components/persona-picker.tsx`, and a new
  `features/personas/components/subagent-allowlist.tsx`.
- **Documentation** — the agent-orchestrator README's session and persona
  sections, and `services/agent-orchestrator/AGENTS.md`'s persona concept.
- **Behaviour change** — a session created after this change spawns no persona
  until one is allowlisted. That is a deliberate contract change, not a
  regression: the alternative leaves the emptiest-looking state the most
  permissive one. Existing sessions are backfilled, and spawning with no persona
  is untouched.

## Non-goals

- **No change to what a persona is.** No new persona fields, no change to
  resolution, narrowing, or the DRA-16 capture rule. This change wires the
  existing object to two places it could not reach.
- **No allowlist over seat personas.** In orchestrated mode a seat's persona is
  chosen by the operator in the roster and is not nameable by any agent, so it is
  not one of "the subagents this session may spawn". It keeps its DRA-30
  validation unchanged.
- **No persona applied to a session's provider, model, or skills.** Stated as a
  non-goal rather than left implicit, because the opposite is the obvious
  expectation: those axes have their own visible controls on the session and are
  deliberately left to them.
- **No freeze on either setting.** Neither joins `session_mode` in becoming
  read-only after the first job.
- **No restyling of the settings panel.** The session persona reuses the existing
  picker; the allowlist is a new component built from the existing toggle row.
