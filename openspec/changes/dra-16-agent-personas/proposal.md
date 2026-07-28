# Add agent personas

## Why

The issue, verbatim:

> **Add agent personas**
>
> Add option to configure custom agent personas, with detailed prompts, skills,
> tools configurations. Starting a subagent should allow the specify a persona.

Today a subagent is a copy of its parent. `spawn_subagent`
(`services/agent-orchestrator/src/agent_orchestrator/runtime/builtin_tools.py`)
creates a child session, copies the parent's model config, copies the parent's
enabled skills, copies the parent's MCP servers, and runs it against a single
fixed subagent system prompt (`SUBAGENT_SYSTEM_PROMPT_PARTS`). There is no way to
say "run this one as a rules lawyer with only the rules skills and no
board-mutating tools" — the only per-child input is the prompt text, which the
parent agent writes at call time and nobody can review, reuse, or version.

Per-seat player configuration (DRA-13, `session_player_configs`) already proved
the shape that solves half of this: a stored row naming provider, model,
reasoning, and skills, resolved against the parent session at spawn time. What it
does not carry is the thing the issue asks for first — a *detailed prompt* — and
it is scoped to one session's four Marvel Champions seats, so it cannot be
reused across sessions or games.

A persona is that same shape, made reusable and given a prompt: a named,
persisted bundle of **a detailed system prompt, a skill selection, and a tool
configuration**, authored once and picked when a subagent is started.

## What Changes

### A persona is a stored, named configuration bundle

- **agent-orchestrator (storage)** — a new `agent_personas` table in the
  orchestrator's PostgreSQL database, migration `0009_agent_personas`, following
  the existing `dragncards_common.schema_migrations` runner and its
  `.postgresql.sql` / `.sqlite.sql` pair. A persona row carries: `name` (primary
  key), optional `display_name` and `description`, `system_prompt`, optional
  `provider_id` and `model_name`, `gateway_options` and `provider_options`,
  `skills_json`, and `allowed_tools_json`, plus `created_at` / `updated_at`.
  Nothing about a persona lives in process memory, in a JSON file in the repo,
  or in the runtime `skills/` directory.
- **agent-orchestrator (API)** — `GET /personas`, `GET /personas/{name}`,
  `PUT /personas/{name}`, `DELETE /personas/{name}`. `PUT` is an upsert, which
  is how `mcps` and `skills` registry writes already behave.
- **agent-orchestrator (validation)** — a persona name is a slug
  (`^[a-z0-9][a-z0-9-]{0,63}$`), the prompt is bounded at 8000 characters, the
  description at 2000, the skill list at 32 entries, and the tool allowlist at
  128 entries. A named provider must be one of the deployment's
  `ENABLED_PROVIDER_IDS`. A named skill must resolve in the skill catalogue, and
  a rejection names the offending skill.

### Personas are scoped to the deployment, not to a user or a session

The orchestrator has no user identity: no authentication, no session cookie, no
owner column on any table, and the dashboard reaches it through an unauthenticated
proxy. So "per user" is not expressible today without inventing an auth model,
and "per session" would defeat the point — the reason a persona exists rather
than a per-seat row is that it outlives one session. Personas are therefore
**global to the deployment**, exactly like the `skill_registries` and
`mcp_registries` tables they sit beside, and the same trade-off applies: anyone
who can reach the API can edit anyone's persona. When identity does arrive, the
migration is an `owner` column plus a scope filter on the list endpoint; the
persona record itself does not change shape.

`name` is the primary key rather than a surrogate UUID, again matching the two
registries next to it, and because an LLM naming `persona: "rules-lawyer"` in a
tool call is usable where a UUID is not. The cost is that renaming a persona is a
delete plus a create.

### A persona is resolved and captured when the subagent starts

`spawn_subagent` gains an optional `persona` argument naming a persona. A session
also gets a `default_subagent_persona`, so a user can pick a persona in the
dashboard and have it apply to every subagent that session spawns without the
agent naming one. An explicit argument wins over the session default.

At spawn time the persona row is read once, resolved against the parent session
(unset provider/model inherit; gateway and provider options overlay the parent's;
`skills_json` of `null` inherits the parent's enabled skills), and **materialised
onto the child**: the child session's model-config row, the child session's
enabled-skill rows, and a `persona` snapshot written into the child session's
`metadata_json`. The snapshot carries the resolved prompt, skills, tool
allowlist, provider, and model, together with the persona name and the
`captured_at` timestamp.

Nothing at child run time re-reads `agent_personas`. That is the answer to
**what happens when a persona is edited or deleted while a subagent started from
it is running: nothing happens to that subagent.** It keeps running the
configuration it was started with, because that configuration is its own rows and
its own metadata, not a pointer into a table someone else can edit. Deleting a
persona therefore needs no reference counting and no soft-delete — it is allowed
unconditionally, and the snapshot on every child ever started from it stays
readable in history afterwards, which is what makes an old transcript
interpretable. The same rule applies to a *queued* child that has not started
executing yet: its configuration was captured when `spawn_subagent` returned, not
when the worker picks it up.

### A persona narrows a subagent's tools; it can never widen them

**A persona may narrow tool access, never widen it.** Concretely:

- A persona does not name MCP servers at all. MCP servers are always inherited
  from the parent session, as they already are for `spawn_subagent` and
  `prompt_player_agent`. There is no field through which a persona could attach a
  server the session does not have.
- `allowed_tools_json` is an **allowlist applied by filtering** the MCP tool
  definitions the child session already exposes. Filtering is a subset operation,
  so a name that is not in the child's catalogue simply does not appear — it
  cannot conjure a tool. The filter is applied to the tool *mapping* as well as
  to the list sent to the model, so a model that guesses a filtered-out tool name
  gets the ordinary `Unknown tool requested` error rather than a live call.
  `null` means "no narrowing".
- `load_skill` and `load_skill_reference` are outside the allowlist and always
  present. The persona's own skill list is unusable without them, and they can
  only read files under the configured skill roots, so they are not a privilege
  surface.
- `provider_id` is validated against `ENABLED_PROVIDER_IDS` on write, so a
  persona cannot reach a provider the deployment has not enabled.

The one axis where a persona *adds* rather than narrows is skills, and that is
deliberate: a persona's whole purpose is to bundle a prompt with the domain
knowledge that prompt assumes, so a persona whose skills had to be a subset of
whatever session happened to spawn it would be useless. This is not a privilege
escalation, because a skill is instruction text — `load_skill` returns markdown
from the skill roots and nothing else — and it can reach nothing the tool
catalogue does not already expose. Per-seat player configuration already works
this way (`session_player_configs.skills_json` names any registered skill), so
this is the established rule rather than a new one.

A persona naming a skill that does not exist, or that has stopped existing since
the persona was written, is rejected **at both ends**: on write with a 400 naming
the skill, and again at spawn time, where the missing skill makes
`spawn_subagent` return an error result naming both the persona and the missing
skill, and no child session or child job is created. The second check is not
redundant — the skill catalogue mirrors the filesystem and is re-synced at every
boot, so a skill can disappear between writing a persona and using it. Failing
loudly is the point: silently dropping an unresolvable skill is the exact bug
DRA-13 had to fix for seat configurations.

### The persona prompt is text, and is treated as text

A persona's `system_prompt` is user-authored text that becomes part of a system
prompt, so:

- It is appended as its own element of the system-prompt parts list, under a
  `## Persona` heading, and joined with the rest. It is never used as a format
  string, never interpolated into a query, a shell command, or generated code,
  and never eval'd. The only thing that happens to it is string concatenation
  into a message body.
- It is bounded at 8000 characters so a persona cannot exhaust a context window
  or a request-body limit by itself.
- It cannot grant capability. Which tools a job has is decided in code from the
  job's own row and the persona's allowlist, so a persona prompt instructing the
  model to "spawn subagents" or "use any tool" changes nothing: subagents have no
  `spawn_subagent` tool to call, and a filtered-out tool is not in the mapping.
- A persona record holds **no credentials**. It names a provider id and a model
  name; API keys stay in the Bifrost gateway configuration where they already
  live, and no persona field is read as a secret. `gateway_options` /
  `provider_options` exist on a persona for the same reason they exist on a
  session model config and a seat config — reasoning travels through
  `gateway_options.reasoning` — and carry no more exposure than those do.

### The dashboard gets a persona editor and a persona picker

- A new `/personas` page: the list of personas, and a form to create, edit, and
  delete one — name, display name, description, prompt, provider, model,
  reasoning, skills, and tool allowlist. One new nav entry beside Play / Games /
  History / Swagger.
- A persona picker in the existing Play settings panel, choosing the session's
  default subagent persona.

Both are new surfaces and are built from the shared Hero UI field components in
`features/shared/components/form-fields.tsx`, so they look like the panels
already there. No existing dashboard component is restyled or re-themed.

## Non-goals

- **Orchestration.** DRA-19 ("Full agents orchestration") wants an orchestrator
  running one stateful subagent per player, with players able to talk to each
  other. This change builds the config layer that will consume: a persona carries
  every axis a seat configuration carries, plus a prompt, so a per-player
  subagent can be started from one. It does not add per-player persona
  assignment, inter-agent messaging, or stateful subagents — a subagent remains
  single-turn with `multi_turn_memory=False`.
- **The subagent list view.** DRA-21 covers that. The persona a child ran with is
  recorded on the child session's metadata and is therefore available to it, but
  no subagent card or list rendering changes here.
- **A persona on `prompt_player_agent`.** Seats have their own stored
  configuration already; layering a persona onto a seat is a merge-precedence
  question that belongs with DRA-19, where per-player personas are the point.
- **Built-in or seeded personas.** No persona ships in the repo. The table starts
  empty and every persona is user-authored, which is what "custom agent personas"
  asks for.
- **Per-user scoping and authorisation.** See the scoping decision above: there
  is no identity in the service to scope to.
- **Renaming a persona in place.** `name` is the key; a rename is a delete plus a
  create.

## Impact

- Affected specs: `agent-orchestrator` (persona persistence, CRUD, validation,
  resolution and capture at spawn, the tool-narrowing rule),
  `llm-capabilities` (`spawn_subagent` takes a persona; the persona catalogue is
  presented to a master job), `dashboard` (persona editor page and the session's
  default-persona picker).
- Affected code, agent-orchestrator: new `storage/models.py` `AgentPersona`, new
  `schema_migrations/sql/0009_agent_personas.{postgresql,sqlite}.sql`, new
  `repositories/personas.py`, new `runtime/personas.py`, new
  `schemas/personas.py`, new `api/routers/personas.py`; plus
  `runtime/builtin_tools.py` (persona argument and resolution),
  `runtime/system_prompts.py` (persona block, persona catalogue),
  `runtime/prompt_run.py` (tool-allowlist filtering, persona prompt),
  `repositories/sessions.py` (default persona, deletion sweep),
  `api/serializers.py`, `api/routers/sessions.py`, `runtime/app.py`.
- Affected code, dashboard: new `features/personas/` (lib + components) and
  `app/personas/page.tsx`; plus `features/shell/components/app-shell.tsx` (one
  nav entry), `features/play/lib/client-api.ts` (persona endpoints),
  `features/shared/lib/types.ts`, and the Play settings panel and session draft
  for the picker.
- Database: one additive migration. A new table and one new nullable column on
  `agent_sessions`; no existing column changes type or meaning, and a deployment
  with no personas behaves exactly as before because both the argument and the
  session default are optional and default to "no persona".
