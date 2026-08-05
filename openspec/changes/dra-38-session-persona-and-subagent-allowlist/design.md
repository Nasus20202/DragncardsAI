# Design

Four decisions carry this change. Each had a defensible alternative, and each is
recorded here with why the alternative was not taken.

## 1. An empty allowlist means "no persona", not "every persona"

This is the decision the whole feature rests on, because it fixes what the control
*is*.

**Chosen: empty means none.** A session with no allowlist rows may spawn no
persona at all. To permit every persona, a session lists every persona.

**Rejected: empty means all.** It reads well in a migration — nothing changes for
anybody — and it is what a naive backward-compatible implementation produces. It
fails on three counts:

- **It inverts the control.** The state that *looks* most restrictive (nothing
  ticked) is the most permissive one. A reader of the API, the database, or the
  settings panel would have to know a convention to read it correctly, and the
  convention is the opposite of what the field name says.
- **It makes "none" inexpressible.** There would be no value meaning "this session
  delegates to no persona" — plausibly the most common thing an operator wants
  from a control like this — short of adding a second boolean beside the list,
  which is two controls where one is needed.
- **The first tick is a silent restriction.** Ticking one persona would go from
  "all allowed" to "one allowed" while the user believes they granted something.

The cost is a real contract change: a session created after this change cannot
spawn a persona until one is allowlisted, and eleven existing tests had to be
updated to say so. That cost is paid once and is the honest price of the rule.

**How the empty case is made unambiguous**, since the rule alone is only as good
as its visibility:

- `GET /sessions/{id}/subagents` returns **every** persona with an `allowed` flag,
  not just the permitted names. There is no empty array to interpret — the shape
  mirrors `GET /sessions/{id}/mcps`, which already reports every registry entry
  with `enabled`.
- The `allowed_subagents` list on the session response and on both request bodies
  carries the rule in its OpenAPI `description`, in capitals. That text is also
  the description of the MCP tool generated from the schema, so a model reads it
  too.
- The refusal at spawn time has a distinct empty-case message ("this session does
  not permit starting a subagent from any persona") rather than a generic message
  listing "none".
- The dashboard states which of the two states the session is in, in words, above
  the toggle list, and never leaves it to the ticks.

**Backward compatibility** is handled by data rather than by weakening the rule:
migration `0013` backfills the allowlist of every session that existed when it ran
with the whole persona catalogue. Nothing in flight loses a capability; new
sessions start closed.

## 2. Enforcement lives in `_resolve_spawn_persona`, at dispatch

**Chosen:** the check is the first thing `_resolve_spawn_persona` does after
working out which persona name applies, above the `repository.get_persona` lookup,
in `runtime/builtin_tools.py`.

That function is the single funnel through which every spawn's persona is decided.
Putting the check there means it covers, with one implementation:

- a model naming a persona in the `spawn_subagent` argument;
- a session's `default_subagent_persona` falling through when the model names
  none — which matters, because a configuration field that walked around the
  allowlist would make the allowlist optional;
- any caller reaching the same path over HTTP or through the service's own MCP
  server, since both drive prompts rather than spawning directly.

It refuses **before** the persona row is read and before any child session, child
job, model-config row, skill row or event is written, so a refused spawn leaves no
trace beyond the refusal itself.

**Rejected: the tool loop in `prompt_run`, beside the seat guard.** That is where
DRA-30's seat check sits, and the instruction to follow it was considered. The
seat guard belongs there because it applies to *every* tool a seat can call and
must therefore sit above the builtin/MCP split. This check applies to exactly one
argument of exactly one builtin tool. Putting it in the loop would mean the loop
inspecting `spawn_subagent`'s arguments by name — a layering inversion that puts
one tool's semantics into the dispatcher — and it still would not cover the
`default_subagent_persona` path, because that name never appears in the arguments
at all. The property the instruction is protecting (server-side, on the dispatch
path, not bypassable by a direct API call) is fully preserved.

**Rejected: filtering the system-prompt catalogue only.** The catalogue *is*
filtered to the allowlist, so a model is not invited to name something it cannot
have. But a model can name a persona the catalogue never mentioned, so this is
presentation and is documented as such in `_persona_catalogue_section`.

**Proof.** `test_a_persona_off_the_allowlist_is_refused` and its three siblings in
`tests/unit/test_builtin_tools_personas.py` fail on `is_error`, on the message,
and on the session count when the check is removed;
`test_a_disallowed_subagent_persona_is_refused_over_the_api` in
`tests/integration/test_api_subagents.py` drives the whole thing over HTTP with no
dashboard involved.

## 3. A session persona applies its prompt and tool allowlist, and nothing else

**Chosen:** `session_persona` contributes the persona's `system_prompt` and its
`allowed_tools`. The session's provider, model, gateway options, provider options
and skills stay exactly as its own controls set them.

**Rejected: materialise the whole persona, as a spawned child does.** Consistency
argues for it, and for a persona that leaves provider/model/skills unset it would
be a no-op anyway. It breaks on a mechanical fact: applying them means writing
`session_model_config` and `session_enabled_skills` — the same two row sets the
settings panel writes from its provider picker, model picker and skill toggle
list. The two writers would fight on every save, and whichever ran last would win,
so the visible pickers would misreport what the agent runs with. A spawned child
has no competing control, which is exactly why the child materialises everything
and the session does not.

The snapshot written for a session therefore records only `name`, `display_name`,
`system_prompt` and `allowed_tools` — a dedicated `session_persona_snapshot_for`
rather than `ResolvedPersona.as_snapshot()`. Recording a provider and a skill list
that are not applied would tell the next reader they were.

## 4. Storage: a name column plus a server-owned snapshot in metadata

**Chosen:** `agent_sessions.session_persona VARCHAR(64)` holds the name; the
resolved snapshot goes under the `agent_persona` key of `metadata_json`, written
by the router when the name is set.

The name is a real column for the reason `session_mode` is one: it gates behaviour
and must not be settable through the free-form metadata blob a client may write.
The snapshot goes in metadata because that is where a spawned child's already
lives, so `session_persona_snapshot`, `persona_prompt_from_snapshot`,
`persona_allowed_tools_from_snapshot` and `narrow_tool_definitions` all apply
unchanged — one reader for both levels, and one place where "editing a persona
does not change a run" is implemented.

Because that key now means something on a session a client can `PATCH`, the router
owns it: a `metadata` write has the stored snapshot merged back over whatever the
client sent, so a client can neither forge a snapshot (giving the session
instructions and a tool allowlist no persona row ever contained) nor drop one by
writing metadata that omits it.

**Rejected: a second JSON column for the snapshot.** It removes the need for the
merge guard, at the cost of two sources of truth for "what persona is this session
running as" and a branch in every reader. The guard is one small, directly tested
rule; the branch would be permanent.

**Rejected: re-resolving the persona at every job start.** Simplest of all, and
wrong: it is precisely the behaviour DRA-16 rejected for subagents. A persona
edited between two turns of the same conversation would retroactively change what
the agent was for the turns already in the transcript.

## Freezing, and why neither setting is frozen

`session_mode` returns `409` after the first job because an orchestrated session's
seats own persistent sessions recorded against it: leaving the mode would abandon
them, entering it would seat-scope a conversation whose agent holds no seat.

Nothing is keyed to `session_persona` or to the allowlist. No rows point at either,
so changing either orphans nothing.

- **The persona is editable** for the same reason the model config is: it is a
  configuration of how the agent behaves from here on, and the capture rule
  guarantees the turns already taken keep the snapshot they ran under. DRA-30 made
  the per-seat persona editable from the roster on the same reasoning.
- **The allowlist is editable, and this is the stronger case.** A security control
  that becomes read-only once a game is under way cannot be used to withdraw a
  persona from a session that is misusing it — which is the one moment the control
  matters most. Tightening takes effect on the next spawn; loosening is an
  explicit operator action.

The API and the dashboard agree: neither field is disabled in the settings panel
after the first job, and the mode picker's `disabled` state remains the only one
there.

## Two things left alone, and why

- **Seat personas.** In orchestrated mode `session_player_configs.persona` is set
  by the operator in the roster and is not nameable by any agent, so it is not one
  of "the subagents this session may spawn". Bringing it under the allowlist would
  couple two controls with different owners and could fail a seat mid-game for a
  choice a human made deliberately. It keeps its DRA-30 validation.
- **`_resolve_spawn_persona`'s "no persona named X" branch.** It looks unreachable
  once every allowlisted name is known to resolve, but the allowlist is read from
  the loaded session while the persona row is a separate read, so a persona deleted
  between the two is genuinely gone by the time it is fetched. The branch is kept,
  with the race named in a comment.
