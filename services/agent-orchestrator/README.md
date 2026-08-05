# Agent Orchestrator

`agent-orchestrator` is the LLM harness service.

It manages durable agent sessions, model/provider configuration, skill assignment, MCP assignment, prompt execution, background jobs, and streamable job events.

It does not replace `game-service`.
Instead, it assigns MCP servers such as `game-service` to an agent session and lets the worker call those tools during prompt execution.

## Run

From the repo root:

```bash
scripts/run.sh start agent-orchestrator
```

Inside the service directory:

```bash
uv run agent-orchestrator
```

Default local URL:

```text
http://localhost:4002
```

## What This Service Is For

Use `agent-orchestrator` when you need to:

- create persistent agent sessions
- choose which provider/model an agent should use
- list supported providers
- list available skills for picker-style UI flows
- assign local skills from `../../skills/<skill_name>` or `../../.opencode/skills/<skill_name>` when running from the service directory
- assign MCP servers like `game-service`
- inspect the effective tool catalog exposed to a session
- submit prompts as background jobs
- inspect job progress and results
- stream job events for a frontend or client

## Provider Configuration

Provider support is configured in two layers.

For Docker Compose, the agent-orchestrator runtime env should live in:

```text
services/agent-orchestrator/.env
```

This file is only for agent-orchestrator runtime settings.

For direct local runs from `services/agent-orchestrator`, set skill roots back to the repo-level skill directories:

```text
SKILL_ROOTS=../../skills
```

For Docker Compose, this file is optional. If it does not exist, agent-orchestrator uses its built-in application defaults, which keeps CI and pipeline parsing from failing on missing local-only env files.

### 1. Bifrost knows how to talk to providers

This is configured in:

```text
services/bifrost/config.json
```

Provider credentials for Bifrost should live in:

```text
services/bifrost/.env
```

That keeps API keys and Bifrost-specific network config with the Bifrost service instead of mixing them into agent-orchestrator envs.

For Docker Compose, `services/bifrost/.env` is also optional. CI can parse the compose files without local secrets, while local runs still pick them up automatically when the file exists.

### 2. Agent Orchestrator decides which providers are enabled

Use this env var:

```text
ENABLED_PROVIDER_IDS
```

Example:

```text
ENABLED_PROVIDER_IDS=mistral,nvidia
```

Only providers in that list are:

- returned by `GET /providers`
- accepted by `PUT /sessions/{session_id}/model-config`

## How To List Providers

Use:

```text
GET /providers
```

This returns only enabled provider IDs, the model prefix used when routing through Bifrost, the currently available models reported by Bifrost, and per-provider availability/error state.

Supported provider IDs include `nvidia`, `openrouter`, `mistral`, `claude`, `openai`, `lmstudio`, and `gemini`.

To avoid hitting Bifrost on every provider-picker refresh, agent-orchestrator keeps a Valkey TTL cache for provider model lists. Configure it with:

```text
PROVIDER_MODELS_CACHE_TTL_SECONDS=600
```

Set it to `0` to disable caching.

The exact response depends on `ENABLED_PROVIDER_IDS`.

### Resilient Listing

Each provider's model-listing call to Bifrost is bounded by a short per-provider timeout so a provider missing an API key fails fast (returns `available=false`) instead of stalling the whole `/providers` response for the full ~60s gateway timeout. Configure the timeout with:

```text
BIFROST_LIST_MODELS_TIMEOUT_SECONDS=8
```

Unavailable providers are then negatively cached in Valkey, so repeat `/providers` calls fast-fail without re-incurring the timeout. Control how long the negative marker lives (must be positive) with:

```text
BIFROST_UNAVAILABLE_CACHE_TTL_SECONDS=600
```

A successful listing clears the negative marker. The remaining enabled providers degrade gracefully: one unavailable provider never blocks the others from being listed.

### Refreshing the Cache

After adding or fixing an API key you do not have to wait for the TTLs to expire:

- `POST /providers/refresh`
  Clears the cached provider model listings (positive and negative entries) for every enabled provider and reports a summary.

- `GET /providers?refresh=true`
  Bypasses the cache for a single call, forcing an immediate re-probe of every enabled provider.

If a provider returns `available: false`, check that:

- the provider is present in `ENABLED_PROVIDER_IDS`
- the matching API key or base URL is set in `services/bifrost/.env`
- `bifrost` has been restarted after the env change
- the negative cache has been cleared (`POST /providers/refresh` or `GET /providers?refresh=true`)

## Endpoint Guide

### Meta

Use these first when integrating the service.

- `GET /health`
  Simple liveness check.

- `GET /ready`
  Reports readiness for database, Bifrost, and worker loop.

- `GET /providers`
  Lists enabled provider IDs, currently available models, plus `available` and `error` for each provider.
  Accepts `?refresh=true` to bypass the model cache for one call.

- `POST /providers/refresh`
  Clears the cached provider model listings (positive and negative entries) for every enabled provider so the next `/providers` call re-probes Bifrost.

### Catalog

Use these to populate selection UIs before a session is configured.

- `GET /providers`
- `POST /providers/refresh`
- `GET /skills`

`GET /skills` returns discovered skills with their path and markdown content, plus
`references`: the skill's markdown reference files by path relative to the skill
directory. Those are exactly the names `load_skill_reference` accepts, so a
consumer can offer a listed entry and have the selection resolve. The field is
always present — empty for a skill with no references — so nobody has to tell "no
references" apart from "not reported".

### Sessions

Use these to create, inspect, update, and terminate agent sessions.

A session runs in one of two **modes**, recorded on the session as `session_mode`:

- `chat` (the default) — one agent talks to the user and spawns memoryless
  subagents on demand. This is the original flow and is unchanged.
- `orchestrated` — the session's agent coordinates a full multi-player game and
  prompts one **persistent** agent per player seat. Each seat's session keeps its
  context for the length of the game, so a seat prompted in a later round still
  knows what it drew, played, and agreed with other seats.

`POST /sessions` accepts `session_mode`; `PATCH /sessions/{session_id}` accepts it
too, but a change is refused with **409** once the session has run a job, because an
orchestrated session's seats own persistent sessions recorded against them.

In orchestrated mode a seat's session is created the first time the seat is
prompted (its id is reported as `agent_session_id` on the seat, which is how a user
reads that player's own context), is *not* terminated when one of its jobs ends, and
is terminated when the seat is deleted or the orchestrating session is terminated.
A seat may also name a `persona`; it is validated when the seat is configured and
snapshotted onto the seat's session when that session is created, so editing the
persona mid-game never changes a seat already playing.

A player agent's output reaches the orchestrator only inside a server-built
`player_report` envelope: the seat id and job status are fields the server sets from
the seat's own session, and the seat's text sits in one delimited block labelled as
untrusted data. Player text never enters the orchestrator's system prompt.

- `GET /sessions`
- `POST /sessions`
- `GET /sessions/{session_id}`
- `GET /sessions/{session_id}/jobs`
- `PATCH /sessions/{session_id}`
- `POST /sessions/{session_id}/terminate`

`GET /sessions` supports:

- `status`
- `limit`
- `offset`

Both `GET /sessions` and `GET /sessions/{session_id}/jobs` return a `page` object with `limit`, `offset`, and `total` for UI pagination.

### Session Configuration

Use this to attach an enabled provider/model to a session.

- `PUT /sessions/{session_id}/model-config`

Typical payload:

```json
{
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "gateway_options": {},
  "provider_options": {}
}
```

Reasoning-capable models can be configured through `gateway_options.reasoning`.

Example:

```json
{
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "gateway_options": {
    "reasoning": {
      "effort": "high",
      "max_tokens": 4096
    }
  },
  "provider_options": {}
}
```

agent-orchestrator requests streamed chat completions from Bifrost for prompt execution.
Transient chunk events are fanned out across replicas through the dedicated orchestrator Valkey instance and then exposed on the job SSE endpoint.

When reasoning is enabled:

- live `reasoning` chunks are sent over the SSE job stream and are not persisted to PostgreSQL

Always:

- live streamed `model_output` chunks are sent over the SSE job stream and are not persisted to PostgreSQL
- final completion state, tool events, failures, cancellations, and the completed output remain persisted

In the dashboard UI, the session settings drawer now includes first-class controls for:

- enabling reasoning stream
- choosing reasoning effort
- setting reasoning max tokens

Those controls write the `gateway_options.reasoning` block for you. The advanced JSON editor is still available for manual overrides and other provider-specific settings.

### Session Skills

Use these to manage skills discovered from the configured `SKILL_ROOTS` entries.

- `GET /sessions/{session_id}/skills`
- `POST /sessions/{session_id}/skills`
- `PATCH /sessions/{session_id}/skills/{skill_name}`
- `DELETE /sessions/{session_id}/skills/{skill_name}`

Any skill found in the skill roots can be enabled; enabling registers it first if
needed, so a skill never enabled before — or added to disk after startup — still
works. A skill that is not on disk is rejected with `400 Unknown skill`.

Enabling is a soft toggle: disabling flips a flag rather than deleting the row.
Disabling is therefore idempotent — disabling a skill that is already off, or was
never enabled, succeeds and changes nothing, so a client can safely replay the
skill set it wants. Only a session that does not exist is a `404`. Endpoints that
report a session's skills list only the enabled ones, and a disabled skill is
withdrawn from the agent: it leaves the system prompt and can no longer be loaded
with `load_skill`.

### Session Player Agents

Use these to configure a roster of player agents for an orchestrated multi-player game — one seat
per hero, each with its own provider, model, reasoning effort, and skills, so two configurations can
play the same cooperative game and be compared afterwards.

- `GET /sessions/{session_id}/players`
- `PUT /sessions/{session_id}/players/{player_id}`
- `DELETE /sessions/{session_id}/players/{player_id}`

`player_id` is one of `player1`..`player4`, matching DragnCards' seat naming.

Every field is optional and an **unset field inherits from the session**, so a comparison only has to
state the axis that differs:

```json
{
  "display_name": "Spider-Man",
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "reasoning": { "enabled": true, "effort": "high" },
  "skills": ["marvel-champions-learn-to-play"],
  "gateway_options": {},
  "provider_options": {}
}
```

- `provider_id` / `model_name` unset — inherit the session's model config.
- `gateway_options` / `provider_options` — *overlaid* on the session's, not replacing them.
- `reasoning` — folded into the resolved `gateway_options.reasoning`; `{"enabled": false}` removes it.
- `skills` unset — inherit the session's enabled skills; a list (including `[]`) overrides them.
- MCP servers are always inherited from the session.

When a session has a roster, its master prompt jobs gain the `list_player_agents` and
`prompt_player_agent` built-in tools. `prompt_player_agent` spawns a child session configured from
that seat's row, tagged with the seat id and the session's `game_id`, so every move the seat records
is attributed to it without inference. Pair it with the standard `wait_for_subagent`. The
`marvel-champions-orchestrator` skill is the playbook for driving this.

#### Seats talk to each other, not to the orchestrator

A seat job of an orchestrated session gains a `send_player_message` built-in taking a
`recipient_player_id` and a `body`. The recipient must be another configured seat of the same
orchestrating session; the sender is the caller's own seat identity, read from its session metadata
and never from the arguments, so a body claiming to be from another seat changes nothing. There is no
recipient value that reaches the orchestrator — it is not a seat, so the roster lookup cannot return
it. A seat reports to the orchestrator by finishing its turn, which is the whole of that direction.

Messages are rows in `player_messages` (migration `0012`), keyed on the **orchestrating** session
because that is the only id the sender and the recipient share. Delivery is **pull**: at the start of
a seat's next invocation its undelivered messages are marked delivered and framed as untrusted data
attributed to the sending seat, in the same `<<<PLAYER_OUTPUT>>>` block a `player_report` uses,
inside a user-role message ahead of the seat's own prompt. Marking is conditional, so two concurrent
invocations of one seat cannot both deliver the same message. Pull rather than push because a player
agent exists only while it is running a job: a message reaches a seat when that seat next plays,
which is the latency a table of humans has.

#### Illegal actions are reported, undone by the seat, and closed only by verification

The orchestrating job of an orchestrated session gains `report_illegal_action` (seat, `violation`,
`required_undo`, optional `round_number`) and `resolve_illegal_action` (`finding_id`,
`resolution_note`). Both record an `illegal_action_finding` job event, durably and on the live bus,
with `status` distinguishing the two.

Findings are rows in `player_illegal_actions` (migration `0012`). Every **open** finding against a
seat is carried into **every** invocation of that seat, framed the same way a message is, until it is
resolved — so a seat cannot outlast a violation by ignoring one turn. The seat performs the undo with
its own game tools and can re-read its findings with the read-only `list_my_illegal_actions`; it has
no tool that closes one. Resolution is conditional on the finding still being open, so a second
resolve is a no-op rather than a second resolution.

That asymmetry is the point: legality is decided from game state, and a seat's claim to have undone
something is a claim to verify, never the verification. `resolve_illegal_action` says so in its own
description, because the party reading it is a model.

A finding also reaches the durable timeline: `HistoryEventEmitter.emit_illegal_action` publishes it as
an `illegal_action` history event (`actor: "agent"`, carrying the seat, the violation, the required
undo, the `open`/`resolved` status and any resolution note). It is a new *event type* rather than a new
actor because history-service pins `actor` to a fixed set — which is also why eval-service identifies a
move by event type and not by the actor alone, so a finding is never graded as a play. The eval-service
judge is then given the round's findings as recorded evidence to weigh, not as a verdict.

### Agent Personas

A **persona** is a reusable, user-authored bundle of the three things that make one agent behave
differently from another: a detailed system prompt, a skill selection, and a tool configuration. A
subagent can be started from one, so "run this child as a rules lawyer with only the rules skills and
no board-mutating tools" is a stored configuration rather than a prompt someone retypes.

- `GET /personas`
- `GET /personas/{name}`
- `PUT /personas/{name}` — upsert
- `DELETE /personas/{name}`

Personas live in the `agent_personas` PostgreSQL table (migration `0009`) and are **global to the
deployment**, keyed by name, exactly like the skill and MCP registries beside them. The service
carries no user identity to scope them to, and per-session scoping would defeat the point — outliving
one session is why a persona exists rather than a per-seat row. `name` is the identity, so renaming a
persona is a delete plus a create, and an agent can name a persona in a tool argument.

```json
{
  "display_name": "Rules Lawyer",
  "description": "Checks rule interactions against the printed rules.",
  "system_prompt": "Answer only from the printed rules. Cite the rule you used.",
  "provider_id": "openai",
  "model_name": "gpt-4o-mini",
  "reasoning": { "enabled": true, "effort": "high" },
  "skills": ["marvel-champions-learn-to-play"],
  "allowed_tools": ["game-service_get_game_state"],
  "gateway_options": {},
  "provider_options": {}
}
```

- `provider_id` / `model_name` unset — inherit the spawning session's model config. A named provider
  must be in `ENABLED_PROVIDER_IDS`.
- `gateway_options` / `provider_options` — *overlaid* on the session's, not replacing them.
- `reasoning` — folded into the resolved `gateway_options.reasoning`; `{"enabled": false}` removes it.
- `skills` unset — inherit the session's enabled skills; a list (including `[]`) overrides them. A
  named skill must resolve in the skill catalogue, and a rejection names the skill.
- `allowed_tools` unset — the child keeps every MCP tool its session exposes. See the narrowing rule
  below.
- Bounds: name is a lowercase slug of at most 64 characters, `system_prompt` at most 8000 characters,
  `description` at most 2000, `skills` at most 32 entries, `allowed_tools` at most 128. These are
  module constants in `runtime/personas.py`, not environment variables, matching `MAX_PLAYER_SKILLS`
  and the conversation-context bounds.

A persona holds **no credentials**. It names a provider and a model; API keys stay in the Bifrost
gateway configuration and no persona field is read as a secret.

#### Starting a subagent from a persona

`spawn_subagent` takes an optional `persona` argument. A session may also record a
`default_subagent_persona`, which applies when the agent names none; an explicit argument wins over
the default. Setting a session default to a persona that does not exist is rejected, and deleting a
persona clears it from any session that defaulted to it. With no persona anywhere, a spawn behaves
exactly as it did before personas existed: the child copies the parent's model config, skills, and
MCP servers.

Master prompt jobs see the persona catalogue — names and descriptions only — in their system prompt,
so the agent can pick one. A persona's own prompt is the *child's* instruction and is never inlined
into the parent's context.

#### A persona is captured at start time and never re-read

When a subagent is started from a persona, the resolved persona is **materialised onto the child**:
the child session's model-config row, the child session's enabled-skill rows, and a persona snapshot
in the child session's metadata holding the resolved prompt, skills, tool allowlist, provider, model,
persona name, and capture time. Nothing at child run time reads `agent_personas` again.

That is deliberate and load-bearing: **editing or deleting a persona does not change any subagent
already started from it**, running or still queued. A subagent must not silently change behaviour
mid-game because someone edited a row. It also means deletion needs no reference counting, and the
snapshot on every past child stays readable so an old transcript remains interpretable.

A persona's named skills are re-validated at spawn time as well as on write, because the skill
catalogue mirrors the filesystem and is re-synced at every boot. A skill that has vanished fails the
spawn with an error naming the persona and the skill, and no child session or job is created —
silently dropping it is the bug that has to be avoided.

#### A persona narrows tool access and can never widen it

This is a security invariant, not a convenience:

- `allowed_tools` is an **allowlist applied by filtering** the MCP tool definitions the child session
  already resolved. Filtering is a subset operation, so a name the child's catalogue does not contain
  simply does not appear. The filter is applied to the dispatch mapping as well as to the list sent
  to the model, so a tool a persona excluded cannot be invoked by naming it directly — it comes back
  as `Unknown tool requested`.
- A persona does not name MCP servers at all. They are always inherited from the spawning session, so
  there is no field through which a persona could attach a server the session does not have.
- `load_skill` and `load_skill_reference` sit outside the allowlist and are always present: a
  persona's own skill list is unusable without them, and they read only from the configured skill
  roots.
- `provider_id` is validated against `ENABLED_PROVIDER_IDS` on write, so a persona cannot reach a
  provider the deployment has not enabled.
- A persona's prompt cannot grant capability. Tool availability is computed from configuration, never
  read out of prompt text, so a prompt claiming the child has `spawn_subagent` changes nothing.

The one axis where a persona *adds* rather than narrows is skills, and that is intentional: a persona
exists to bundle a prompt with the domain knowledge that prompt assumes. A skill is instruction text
— `load_skill` returns markdown from the skill roots — and reaches nothing the tool catalogue does not
already expose, so this is not an escalation. Per-seat player configuration already works this way.

### Waiting On A Child

`wait_for_subagent` always returns. The child job's persisted status is the authority, not its live
event stream: the stream is ephemeral and is not written on every terminal transition, so the wait
re-reads the child's row whenever the child falls silent. A crashed child therefore ends the wait
with its `error_code` and message rather than stalling until the budget runs out.

```text
SUBAGENT_WAIT_TIMEOUT_SECONDS=600        # absolute budget for one wait, not per event
SUBAGENT_WAIT_POLL_INTERVAL_SECONDS=5    # how long the child may be silent before the row is re-read
```

When the budget expires, the parent is told the child's last recorded status and that it must stop
waiting, and a `subagent_failed` event with `reason: "wait_timeout"` is recorded on the parent job so
the stall is visible in the session timeline. A job orphaned by a hard worker kill (SIGKILL, OOM)
still stays `running` — nothing reclaims it yet — but it can no longer hold a parent hostage.

### Asking The User

Master prompt jobs also get an `ask_user` built-in tool, so a decision that belongs to the human is
put to them as clickable choices instead of being guessed at or deferred to a new turn. The model
supplies the question and between one and eight `{label, value}` choices, and may set
`allow_free_text` to let the user type an answer of their own.

The tool **blocks** while it waits. A job cannot suspend, so the wait happens inside the tool call,
exactly as `wait_for_subagent` does, and the answer comes back as an ordinary tool result. The pending
question lives in the `job_questions` table, not in the waiting worker's memory: the request that
answers it is a different process and may be a different replica, and the question has to survive a
browser reload and a stream reconnect.

```text
ASK_USER_TIMEOUT_SECONDS=600         # absolute budget for one question, not per poll
ASK_USER_POLL_INTERVAL_SECONDS=2     # how often the stored question is re-read while waiting
```

The wait always ends. When the budget expires the question is closed with reason `timeout`, a
`user_question_closed` event is recorded on the job, and the model is told nobody answered and to
continue on its own judgement — deliberately *not* as an error result, which would invite it to ask
the same question again immediately. Requesting the job's cancellation closes the question with reason
`cancelled`.

Answer a question with:

- `POST /jobs/{job_id}/questions/{question_id}/answer`
  Body is exactly one of `{"choice_value": "<one of the offered values>"}` or `{"text": "..."}`.

The submitted choice is validated against the choices stored on the question, so a client can neither
answer with something the model never offered nor widen what was asked. A question is answerable
once: a second answer, an answer to a closed question, and an answer to a question whose job has
already finished all return `409`. Choice labels and values are model-authored text, and the dashboard
renders them as plain text, never as markup.

### Session Tools

Use this to inspect the tool list that the worker will expose to the model after MCP assignments are attached.

- `GET /sessions/{session_id}/tools`

### Session MCPs

Use these to assign tool surfaces the worker may call.

- `GET /sessions/{session_id}/mcps`
- `POST /sessions/{session_id}/mcps`
- `DELETE /sessions/{session_id}/mcps/{assignment_name}`

Typical `game-service` MCP assignment:

```json
{
  "name": "game-service",
  "transport": "streamable-http",
  "server_url": "http://localhost:4001/mcp/",
  "headers": {}
}
```

For local host clients talking to Dockerized services:

- use `http://localhost:4002` for requests into `agent-orchestrator`
- use `http://game-service:8000/mcp/` inside MCP assignments that will be used by the `agent-orchestrator` container

`POST /sessions/{session_id}/mcps` normalizes `streamable-http` MCP URLs to include the trailing slash automatically.

### Prompt Submission

Use this when you want the agent to do work.

- `POST /sessions/{session_id}/prompts`

This does not run inline.
It creates a prompt run, enqueues a background job, and returns immediately.

### Jobs

Use these to inspect the outcome of a prompt or stop it.

- `GET /jobs/{job_id}`
- `GET /jobs/{job_id}/status`
- `POST /jobs/{job_id}/cancel`
- `GET /sessions/{session_id}/jobs`

`GET /jobs/{job_id}` includes:

- `latest_event_id`
- `latest_event_type`
- `available_tools`
- `events`
- `outputs`

`GET /sessions/{session_id}/jobs` supports:

- `status`
- `limit`
- `offset`

`GET /jobs/{job_id}/status` is a lightweight polling endpoint that returns only the job summary.

This shape is intended to be usable directly by a future UI without additional aggregation.

### Job Events

Use these for polling or frontend streaming.

- `GET /jobs/{job_id}/events`
  Replay persisted events, optionally with `?after=<event_id>`.

  Supports optional `?event_type=<name>` filtering.

- `GET /jobs/{job_id}/events/stream`
  Stream events as Server-Sent Events.

Event types include:

- `progress`
- `reasoning`
- `model_output`
- `tool_call`
- `tool_result`
- `skill_loaded`
- `compaction`
- `compaction_failed` — automatic compaction could not complete; the turn ran on the history it
  already had. Carries the failure `code`, its `message`, and the `usage_ratio` that triggered the
  attempt
- `subagent_started`
- `subagent_completed`
- `subagent_failed`
- `user_question` — the agent asked the user something, with the offered choices
- `user_question_answered` — the answer that was recorded
- `user_question_closed` — the question stopped awaiting an answer (`timeout` or `cancelled`)
- `seat_scope_violation` — a player seat's tool call named another seat's cards and was refused
  before the tool ran. Carries the caller's `player_id`, the `foreign_player_id` it reached for, the
  `tool_name`, and the `argument`/`value` that named it. Orchestrated mode only
- `illegal_action_finding` — the orchestrator recorded, or resolved, a finding that a seat's action
  broke the rules. Carries the `finding_id`, the `player_id` it concerns, the `violation`, the
  `required_undo`, and a `status` of `open` or `resolved`. Orchestrated mode only
- `completion`
- `failure`
- `cancellation`

Only `completion`, `failure`, and `cancellation` are terminal and close the SSE stream. The three
`user_question*` events are not, so the stream stays open while the user decides.

#### When Valkey Is Unavailable

Every event above is written to PostgreSQL before it is published to the Valkey live bus, and the
SSE endpoint polls the persisted rows as well as forwarding the bus. So the bus is a latency
optimisation, not a system of record, and a transport failure on it degrades rather than fails:

- **Publishing is best-effort.** A failed publish is logged and the caller carries on. It cannot
  fail a job, abort a streaming model response, or make a job miss its terminal status. Writes to
  PostgreSQL still raise as before.
- **The SSE stream degrades to poll-only.** A failed live read does not end the response; the
  stream keeps serving persisted events on a short backoff and resumes live delivery once the bus
  recovers. A job that finishes while the bus is down still closes its stream normally.
- **Clients lose latency, not events**, with one exception: `compaction` is the only event whose
  durable home is a separate compaction job rather than a row on the job being compacted, so
  dropping its live copy means the summary appears on the next session load instead of immediately.
- **Logs stay readable.** A publish happens once per streaming delta, so a sustained outage emits
  one traceback, a thinning trail of counted warnings, and one recovery line naming the streak
  length — not one stack per failure.

### Context Management

- `GET /sessions/{session_id}/context` — current context health: the estimated next-request size,
  the model's context window, the usage ratio, the compaction count, and the token breakdown.
- `POST /sessions/{session_id}/compact` — compact now. The body is optional; `from_session_start`
  re-reads the whole session instead of the span since the last checkpoint.

When `multi_turn_memory` is enabled, a job estimates its replay before its first model request and
compacts when the ratio against the model's context window reaches `CONTEXT_COMPACTION_THRESHOLD`.

Compaction summarizes into a `CompactionRecord` and writes a synthetic `job_type='compaction'` job
so the summary is visible in the transcript. Raw `job_events` rows are never deleted, so a summary
can always be rebuilt from them.

What the summarizer is given is bounded three ways, so it never grows with the session's total
length:

- **From the previous checkpoint.** A compaction reads only the jobs created after the previous
  record's `covers_up_to_job_id`, and is handed that record's `summary_text` as prior context. The
  manual endpoint's `from_session_start` ignores the checkpoint — the recovery path for a summary
  believed to have lost something. Automatic compaction always uses the checkpointed form.
- **Per event.** One tool call's arguments or one tool result contributes at most
  `CONTEXT_COMPACTION_EVENT_CHAR_BUDGET` characters, followed by a `… [truncated, N chars omitted]`
  marker. This applies to the summarization input only — a tool result replayed to the game agent is
  never truncated, because a half-cut board cannot be told apart from a board that is not in play.
- **In total.** The assembled request is estimated, and while it exceeds
  `CONTEXT_COMPACTION_THRESHOLD` of the window, the oldest entries are dropped. How many were
  dropped and how many events were truncated are logged and carried on the `compaction` event.

```bash
CONTEXT_WINDOW_SIZE=128000                  # fallback when the provider reports no context length
CONTEXT_COMPACTION_THRESHOLD=0.8            # of the window, for both the trigger and the input ceiling
CONTEXT_COMPACTION_EVENT_CHAR_BUDGET=20000  # per tool call or tool result, summarization input only
```

Automatic compaction exists to keep a job inside its context window, so its own failure never fails
that job: the worker logs it, emits `compaction_failed`, and the turn continues on the history it
already has. A manual compaction does report its failure — 502 when the summarizing call fails, 422
when there is nothing to summarize — because the caller asked for it directly.

## MCP Surface

This service exposes its own HTTP API as MCP tools over streamable-HTTP:

```text
http://localhost:4002/mcp/
```

This is the opposite direction from **Session MCPs** above. A session MCP assignment is this
service acting as an MCP *client*, pulling someone else's tools in for the game-playing agent to
call. `/mcp/` is this service acting as an MCP *server*, so a coding agent working on this
repository can create a session, configure it, submit a prompt, and read the resulting job events
as tool calls instead of hand-written HTTP requests.

Tools are generated from this service's OpenAPI schema — nothing is hand-written — so every tool
is exactly the endpoint it came from, with that endpoint's own request and response models, and
**a tool's name is the endpoint's `operation_id`**: `create_session`, `submit_prompt`,
`list_job_events`. A new route therefore becomes a tool on its own; give it an explicit
`operation_id` or the tool inherits FastAPI's generated name.

Some routes are deliberately absent from MCP, declared in
`src/agent_orchestrator/mcp_server.py`:

- `GET /health` and `GET /ready` — probes are noise in a model's tool list.
- `GET /jobs/{job_id}/events/stream` — a tool call reads its response to completion and an SSE
  stream never completes. Poll `GET /jobs/{job_id}/events` with `?after=` instead.
- The writes to the deployment-global registries: `POST`/`DELETE /skills`, `POST`/`DELETE /mcps`,
  and `PUT`/`DELETE /personas/{name}` — one entry changed there changes what every session in the
  deployment resolves. Reading all three stays available, as does the whole per-session
  lifecycle, so an agent can still clean up the sessions it created.

Exclusion applies to MCP only. Every one of those endpoints still works over HTTP, for the
dashboard and for a developer who types it deliberately.

The end-to-end debugging loop this surface exists for — create a game, start a player agent, read
its actions, read the live board, request an evaluation, read the verdict — is documented in the
root [`AGENTS.md`](../../AGENTS.md#driving-the-system-end-to-end).

## Typical Workflow

### Configure a new agent

1. `POST /sessions`
2. `GET /providers`
3. `GET /skills`
4. `PUT /sessions/{session_id}/model-config`
5. `POST /sessions/{session_id}/skills`
6. `POST /sessions/{session_id}/mcps`
7. `GET /sessions/{session_id}/tools`
8. `PUT /personas/{name}` then `PATCH /sessions/{session_id}` with `default_subagent_persona`, when
   the session's subagents should run as a persona rather than as copies of the session

### Run a prompt

1. `POST /sessions/{session_id}/prompts`
2. `GET /jobs/{job_id}` or `GET /jobs/{job_id}/events/stream`
3. `GET /sessions/{session_id}/jobs` when a UI needs recent session history without fetching the full session detail

### Stop a running prompt

1. `POST /jobs/{job_id}/cancel`
2. `GET /jobs/{job_id}`

## Dependencies

The service expects:

- dedicated orchestrator PostgreSQL
- dedicated orchestrator Valkey for transient cross-replica streaming events
- Bifrost
- one or more skill roots, usually `/app/skills` in Docker or `skills` locally
- optional MCP servers such as `game-service`

Set the Valkey connection with:

```text
VALKEY_URL=redis://localhost:6381/0
```

In Docker Compose, agent-orchestrator uses the dedicated `agent-orchestrator-valkey` service.

### Valkey command volume on the streaming path

The shared RESP client opens a fresh TCP connection and emits one `valkey.execute`
span for every command, so a Valkey command, a TCP connection and a span are the
same unit of cost here. Two properties of the live-event path exist to keep that
unit count proportional to work done rather than to tokens streamed or seconds
elapsed, and both are easy to undo by accident:

- **Publishing an event is one command.** Appending to a job's stream and
  re-arming the stream's TTL happen in a single scripted round trip. Splitting
  them back into `XADD` and `EXPIRE` doubles the cost of the busiest path in the
  service, because a streaming model publishes one live event per token.
- **A subscriber reads a batch per command.** `XREAD` asks for up to 64 entries
  and the surplus is buffered inside that one subscriber until it is asked for
  them. Taking a single entry per command made the consumer issue as many
  commands as the producer.

`JOB_EVENT_STREAM_IDLE_BLOCK_SECONDS` (default 15) is the third: it is how long a
quiet SSE stream waits on the live bus before re-reading the job's status from
PostgreSQL. It is a fallback interval, not a latency budget — a published event
ends the wait at once, so nothing the client sees arrives later for making it
long. It must not be set from `WORKER_POLL_INTERVAL_SECONDS`, whose 0.2s is tuned
for how fast the worker claims a queued job; reusing it here cost five Valkey
commands and ten database queries a second per open stream, for the whole life of
a job.

That interval has a counterpart in `LIVE_BUS_DEGRADED_MIN_SECONDS` /
`LIVE_BUS_DEGRADED_MAX_SECONDS` (`runtime/live_event_resilience.py`, 0.5s to 5s):
when a stream's own live reads start failing it polls at that rate instead, so an
outage costs latency rather than the response. The two constants bracket one
narrow case from opposite sides — a publish that fails while the same stream's
reads keep succeeding leaves the stream undegraded and therefore sitting in the
full idle block. It is bounded and accepted; the reasoning, and why shortening
the idle block is the wrong way to cover it, is in
`openspec/changes/dra-37-valkey-call-volume/design.md`. Read that before moving
either constant.

### Publish every event a client waits on

The stream has two sources for the same event: it polls `list_events` and it
forwards the live bus. So a durable row with no matching `publish` still arrives —
but only on the next fallback pass, which is now seconds rather than 200ms.

**When you add an `append_event`, publish it too**, passing the durable row's id as
`durable_event_id=` so the live copy and the polled copy collapse into one
transcript entry instead of rendering twice. Two cases are not optional:

- **Terminal events** (`completion`, `failure`, `cancellation`). Until a terminal
  event is *delivered* the client's stream stays open, so an unpublished one is a
  UI that hangs rather than one that merely lags. This is why `mark_job_cancelled`
  and `request_cancel` return the ids of the rows they append: the repository has
  no bus, so their callers do the publishing.
- **`tool_call` and `tool_result`.** A tool call is recorded before the tool runs,
  which is exactly when the bus falls quiet, so leaving these to the poll makes a
  slow tool look like a stalled agent.

The one durable event deliberately left to the fallback pass is
`progress {"status": "running"}`: it is not terminal, so it cannot hold a stream
open, and the same fact is already on the job row the dashboard renders from.
Anything else you choose to leave, say so where you leave it.

## Browser CORS

`CORS_ALLOW_ORIGINS` is a comma-separated allowlist of browser origins, defaulting
to the local dashboard (`http://localhost:3001,http://127.0.0.1:3001`). It must
never be set to `*`.

Docker Compose publishes 4002 on the host, so under a wildcard allowlist any web
page a developer happens to visit could issue a cross-origin
`DELETE http://localhost:4002/sessions/{id}` — destroying an agent session — or
`POST .../prompts`, spending the owner's model budget. A strict allowlist does not
affect normal use: the dashboard calls this service through its own server-side
proxy (`/api/proxy/orchestrator/...`), including the SSE job streams, which are
`EventSource` calls to relative proxy URLs rather than to port 4002. Those proxied
requests originate in the dashboard's Node process and carry no `Origin` header, so
CORS does not apply to them, and neither does it apply to history-service or any
other server-to-server caller.

**CORS is not authentication.** It stops a browser being used as a confused deputy
for methods that require a preflight; it does not stop a non-browser client, which
simply omits `Origin`. Requiring a credential is tracked separately as DRA-32.

## Tests

From the repo root:

```bash
scripts/test.sh unit agent-orchestrator
scripts/test.sh integration agent-orchestrator
```

From the service directory:

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/integration/ -v
uv run pytest tests/ -v
```
