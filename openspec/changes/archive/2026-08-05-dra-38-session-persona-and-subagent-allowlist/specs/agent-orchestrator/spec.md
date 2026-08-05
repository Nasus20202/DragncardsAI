## ADDED Requirements

### Requirement: A session's own agent may run as a persona
A session SHALL be able to name a persona its **own** agent runs as, distinct from the persona its subagents are started from. The name SHALL be recorded on the session as a first-class field rather than inside the client-writable metadata blob, SHALL be accepted when the session is created and when it is updated, and SHALL be reported on every session response.

A session persona SHALL contribute exactly two things to that session's jobs: the persona's system prompt, delivered as its own clearly delimited section of the assembled system prompt placed after the base rules it cannot override, and the persona's tool allowlist, narrowing that session's tool surface by the same filter a subagent's persona applies. It SHALL NOT change the session's provider, model, gateway options, provider options, or enabled skills, because each of those is set by its own control on the same session and a persona overwriting what those controls write would make them misreport what the agent runs with.

Naming a persona that does not exist SHALL be rejected when the session is written, rather than discovered when a job runs.

#### Scenario: A session records and reports its persona
- **WHEN** a client creates or updates a session naming an existing persona as its own
- **THEN** the session SHALL record that persona
- **AND** every response for that session SHALL report it

#### Scenario: The persona's instructions reach the session's own agent
- **WHEN** a job runs on a session that has adopted a persona
- **THEN** the assembled system prompt SHALL contain that persona's prompt as a delimited section in addition to the base prompt parts

#### Scenario: The persona's tool allowlist narrows the session's tools
- **WHEN** a job runs on a session whose persona carries a tool allowlist
- **THEN** the tools offered to the model and the mapping used to dispatch a call SHALL both exclude every tool outside that allowlist

#### Scenario: The persona does not override the session's model
- **WHEN** a job runs on a session whose persona names a provider and a model
- **THEN** the request SHALL use the provider and model recorded on the session's own model configuration

#### Scenario: A session without a persona is unchanged
- **WHEN** a job runs on a session that has adopted no persona
- **THEN** the assembled system prompt SHALL contain no persona section

#### Scenario: An unknown session persona is rejected
- **WHEN** a client names a persona that does not exist as a session's own persona
- **THEN** the request SHALL be rejected with a client error naming the persona

### Requirement: A session persona is captured when it is assigned
The persona a session adopts SHALL be resolved and captured at the moment the name is set, and the captured record SHALL be what a job reads. Nothing at job run time SHALL re-read the persona table for the session's own persona.

Editing or deleting the persona afterwards SHALL NOT change a session that has already adopted it, for the same reason it does not change a subagent already started from it: a conversation that has taken turns as one agent must not be retroactively rewritten into a different one. Deleting the persona SHALL clear the session's persona **name**, so nothing re-adopts or reports a persona that is gone, and SHALL leave the captured record intact, so the turns already taken stay interpretable.

The captured record SHALL be owned by the server. A client SHALL change a session's persona by naming it, and a client-supplied metadata write SHALL be able neither to introduce a captured record the server did not write nor to remove one the server did write.

The captured record SHALL hold only the fields a session applies, so that it cannot suggest that a provider, a model, or a skill list was captured and then ignored.

#### Scenario: A persona edited later does not change the session
- **WHEN** a session has adopted a persona and that persona's prompt and tool allowlist are then changed
- **THEN** the session SHALL keep the prompt and allowlist captured when it adopted the persona

#### Scenario: A deleted persona clears the name and keeps the record
- **WHEN** a persona a session has adopted is deleted
- **THEN** the session SHALL no longer report that persona as its own
- **AND** the captured record SHALL remain on the session

#### Scenario: A metadata write cannot forge a captured persona
- **WHEN** a client updates a session's metadata with a captured persona record of its own
- **THEN** the server's captured record SHALL be kept and the client's SHALL be discarded

#### Scenario: A metadata write cannot drop a captured persona
- **WHEN** a client updates a session's metadata with a body that omits the captured persona record
- **THEN** the session SHALL keep the captured record and SHALL still report its persona

### Requirement: A session allowlists the personas its agent may spawn
A session SHALL record which personas its agent may start a subagent from. The allowlist SHALL be a per-session selection from the deployment-global persona catalogue, shaped like the session's skill selection: one entry per persona, an entry that is switched off SHALL NOT permit that persona, and an entry SHALL name a persona that exists.

**An empty allowlist SHALL mean that no persona may be spawned.** It SHALL NOT be interpreted as permitting every persona. Spawning a subagent with no persona at all — which copies the session's own configuration — SHALL be unaffected by the allowlist and SHALL remain available to every session.

The allowlist SHALL be manageable both as a whole, in the same request as the session fields it constrains, and one persona at a time, so a client holding a complete configuration and a client making a single change are both served.

Deleting a persona SHALL remove it from every session's allowlist, so no session is left permitting a name that no longer resolves.

#### Scenario: A new session permits no persona
- **WHEN** a session is created without an allowlist
- **THEN** its allowlist SHALL be empty and no persona SHALL be permitted

#### Scenario: A persona is allowed and reported
- **WHEN** a client allows a persona for a session
- **THEN** the session SHALL report that persona as allowed

#### Scenario: A switched-off entry does not permit the persona
- **WHEN** a session's entry for a persona is switched off
- **THEN** the session SHALL NOT report that persona as allowed and SHALL NOT permit spawning it

#### Scenario: Allowing an unknown persona is rejected
- **WHEN** a client allows a persona that does not exist
- **THEN** the request SHALL be rejected with a client error naming the persona

#### Scenario: Deleting a persona withdraws every allowance
- **WHEN** a persona that sessions have allowlisted is deleted
- **THEN** no session SHALL report it as allowed

### Requirement: The empty allowlist is stated, never inferred
Because an empty allowlist is the most restrictive state and an empty list is the shape most easily misread as "unrestricted", the API SHALL make the meaning explicit rather than leaving a caller to interpret an empty array.

Listing a session's permitted subagents SHALL return every persona in the catalogue together with whether that session allows it, rather than returning only the permitted names. Every field that carries the allowlist SHALL state in its published schema description that an empty list means no persona may be spawned.

#### Scenario: The listing states allowed and not allowed per persona
- **WHEN** a client lists a session's permitted subagents and personas exist that the session does not allow
- **THEN** the response SHALL include every persona
- **AND** each SHALL carry whether this session allows it

#### Scenario: The rule is published with the field
- **WHEN** a client or a model reads the schema of a field carrying the allowlist
- **THEN** the description SHALL state that an empty list means no persona may be spawned

### Requirement: The subagent allowlist is enforced when a subagent is started
The allowlist SHALL be enforced by the server at the point a spawn resolves which persona to use, not by whichever client displays it. A spawn naming a persona the session does not allow SHALL be refused, and the refusal SHALL apply however the persona was chosen: named by the agent in the tool call, or reached through the session's recorded default when the agent named none.

A refused spawn SHALL create no child session, no child job, and no subagent-started event. The refusal SHALL state that the restriction is enforced by the server and SHALL name the personas that are permitted, so an agent can correct the call rather than repeat it; when none are permitted the refusal SHALL say so plainly and point at spawning without a persona.

The catalogue of personas offered to an agent in its system prompt SHALL be the session's allowlist rather than the whole deployment catalogue, so an agent is not invited to name something that would be refused. That narrowing SHALL NOT be relied on as the enforcement, because an agent may name a persona the catalogue never mentioned.

#### Scenario: A persona off the allowlist is refused
- **WHEN** an agent calls the spawn tool naming a persona its session does not allow
- **THEN** the spawn SHALL be refused with an error result
- **AND** no child session, child job, or subagent-started event SHALL be created

#### Scenario: An empty allowlist refuses every persona
- **WHEN** an agent of a session with an empty allowlist names any persona on a spawn
- **THEN** the spawn SHALL be refused

#### Scenario: The session default is subject to the allowlist
- **WHEN** an agent spawns without naming a persona and the session's recorded default is not on the allowlist
- **THEN** the spawn SHALL be refused rather than falling through to that persona

#### Scenario: A direct API caller cannot bypass the allowlist
- **WHEN** a caller drives a prompt over the HTTP API whose agent names a persona the session does not allow
- **THEN** the spawn SHALL be refused by the server and no child SHALL be created

#### Scenario: An allowed persona still spawns
- **WHEN** an agent names a persona its session allows
- **THEN** the child SHALL be started from that persona as before

#### Scenario: The offered catalogue is the allowlist
- **WHEN** a top-level job's system prompt is assembled for a session that allows some but not all personas
- **THEN** the persona catalogue in that prompt SHALL list only the allowed personas

#### Scenario: An empty allowlist offers no catalogue
- **WHEN** a top-level job's system prompt is assembled for a session with an empty allowlist
- **THEN** the prompt SHALL contain no persona catalogue

### Requirement: The session default and the allowlist cannot contradict each other
A session's default subagent persona SHALL be one the session allows. A configuration in which the default is not permitted SHALL be rejected rather than stored, because its only observable effect would be a refusal on every plain spawn.

Both fields SHALL be validated against the state the request produces rather than the state already stored, so a single request that allows a persona and makes it the default SHALL succeed. A rejected combination SHALL leave the session unchanged, with neither field written.

Withdrawing a persona SHALL always be possible, but SHALL take the default with it: revoking the persona a session still defaults to SHALL be refused unless the same request also clears the default.

#### Scenario: A default outside the allowlist is rejected
- **WHEN** a client sets a default subagent persona that the resulting allowlist does not contain
- **THEN** the request SHALL be rejected with a client error
- **AND** neither the allowlist nor the default SHALL be changed

#### Scenario: Allowing and defaulting in one request succeeds
- **WHEN** a client allows a persona and names it as the default in the same request
- **THEN** the request SHALL succeed

#### Scenario: Revoking the default persona alone is refused
- **WHEN** a client revokes the persona that is still the session's default
- **THEN** the request SHALL be rejected and the allowlist SHALL be unchanged

#### Scenario: Revoking with the default cleared succeeds
- **WHEN** a client revokes that persona and clears the default in the same request
- **THEN** the request SHALL succeed and the session SHALL permit no persona by default

### Requirement: The session persona and the subagent allowlist stay editable
Neither a session's own persona nor its subagent allowlist SHALL be frozen once the session has run a job, unlike the session mode. No persistent record is keyed to either, so changing either abandons nothing, and the capture rule already guarantees that the turns a session has taken keep the configuration they ran under.

The allowlist in particular SHALL remain editable for the life of the session, because a permission that cannot be withdrawn while a session is running cannot be used at the moment it matters most. A tightened allowlist SHALL take effect on the next spawn.

#### Scenario: The persona changes after the first job
- **WHEN** a client changes the persona of a session that has already run a job
- **THEN** the change SHALL be accepted

#### Scenario: A permission is withdrawn mid-session
- **WHEN** a client removes a persona from the allowlist of a session that has already spawned a subagent from it
- **THEN** the change SHALL be accepted
- **AND** a later spawn naming that persona SHALL be refused

## MODIFIED Requirements

### Requirement: spawn_subagent creates monitored child jobs without blocking
When the `spawn_subagent` built-in tool is invoked the worker SHALL create a child session, configure it with the parent session's model config and skills, enqueue a prompt job with `parent_job_id` set, give the child session a generated display name, and return a tool result immediately containing the `child_job_id` and that `name`. The child job runs concurrently; the parent agent can continue its work without waiting. A background task SHALL monitor the child job, append the child outcome to the parent job's event log, and terminate the child session when the child reaches a terminal state.

The child's name SHALL be generated rather than taken from the prompt, and SHALL be seeded on the child session's own identifier so that no two children share a codename. The name SHALL be stored on the child session and SHALL be the same string in the `subagent_started` event, in the outcome event the monitor appends, and in the tool result — generated once, never recomputed. A caller that supplies a name for the child SHALL have that name used instead; this is how a player agent keeps its seat's own display name.

`spawn_subagent` SHALL accept an optional persona name. When a persona applies — either because the call named one or because the parent session records a default subagent persona — the persona SHALL first be checked against the spawning session's subagent allowlist and SHALL be refused when it is not permitted. When it is permitted, the child SHALL be configured from the resolved persona instead of from a plain copy of the parent's model config and skills, and the persona SHALL be captured onto the child at that moment. MCP servers SHALL be inherited from the parent either way. When no persona applies the child SHALL be configured exactly as before: a copy of the parent's model config and skill assignments, unaffected by the allowlist.

The monitor SHALL resolve the child's outcome the same way `wait_for_subagent` does — from the child's persisted status, with live events short-circuiting the wait — so the reported outcome is the child's actual fate and not a timeout observed because no event was ever published. The `reason` on a `subagent_failed` event SHALL be the terminal status the child reached (`failed`, `cancelled`) or why the monitor stopped observing, and SHALL carry the child's `error_code` and `error_message` when it has them. A child that ended `"interrupted"` produced usable partial work and SHALL be reported as `subagent_completed`.

#### Scenario: Child configured from a named persona
- **WHEN** `spawn_subagent` is called naming a persona the session allows
- **THEN** the child session SHALL be configured from that persona's resolved provider, model, options, and skills
- **AND** the `subagent_started` event payload SHALL name the persona the child was started from

#### Scenario: Child spawned without a persona
- **WHEN** `spawn_subagent` is called with no persona and the session records no default
- **THEN** the child SHALL be configured from a copy of the parent's model config and skill assignments
- **AND** the spawn SHALL succeed whatever the session's allowlist contains

### Requirement: Agent persona persistence
The agent-orchestrator SHALL let a client define named agent personas and SHALL persist them in PostgreSQL rather than in process memory, in a repository file, or in the runtime skills directory. A persona SHALL be a reusable bundle of a system prompt, a skill selection, and a tool configuration, and SHALL carry: a name that identifies it, an optional display name and description, a system prompt, an optional provider id and model name, gateway and provider option overrides, a skill list, and a tool allowlist.

A persona SHALL be scoped to the deployment rather than to a session or a user, because a persona exists precisely to be reused across sessions and because the service carries no user identity to scope to. A persona's name SHALL be its identity, so a persona is addressable by name in an API path and nameable by an agent in a tool argument.

Because a persona is deployment-global, which personas a **given** session may start a subagent from SHALL be a per-session selection from this catalogue rather than a property of the catalogue itself. A persona SHALL therefore be usable by a session that has selected it and unavailable to one that has not, without either session being able to change the catalogue.

A persona SHALL NOT carry provider credentials of any kind. Naming a provider and a model SHALL be the only way a persona refers to provider configuration, and API keys SHALL remain in the gateway configuration.

#### Scenario: Persona is created and read back
- **WHEN** a client writes a persona with a system prompt, a skill list, and a tool allowlist
- **THEN** the persona SHALL be persisted
- **AND** reading that persona by name SHALL return the values that were written

#### Scenario: Persona survives a restart
- **WHEN** a persona has been written and the service is restarted
- **THEN** listing personas SHALL still return that persona with its stored configuration

#### Scenario: Persona write is an upsert
- **WHEN** a client writes a persona whose name already exists
- **THEN** the stored persona SHALL be replaced by the submitted configuration rather than rejected as a duplicate

#### Scenario: Persona is listed and deletable
- **WHEN** a client lists personas
- **THEN** every stored persona SHALL be returned
- **AND** deleting a persona by name SHALL remove it, and deleting a persona that does not exist SHALL return a not-found error

#### Scenario: One deployment catalogue, per-session selection
- **WHEN** two sessions exist and only one allows a given persona
- **THEN** both SHALL be able to read that persona from the catalogue
- **AND** only the session that allows it SHALL be able to start a subagent from it

### Requirement: Subagent jobs use a dedicated system prompt
Subagent jobs SHALL receive a system prompt distinct from the master job prompt.

A job started from a persona — a subagent started from a spawn's persona, or a top-level job whose session has adopted a persona of its own — SHALL additionally receive that persona's system prompt as its own clearly delimited section of the assembled prompt. The persona prompt SHALL be treated purely as text: it SHALL be concatenated into the message body and SHALL NOT be used as a format string or interpolated into any context where text becomes code, a query, or a shell command. The persona prompt SHALL NOT determine which tools the job has, because tool availability is decided from the job's own configuration.

#### Scenario: Subagent receives subagent-specific prompt
- **WHEN** a job with a non-null `parent_job_id` starts execution
- **THEN** the system prompt SHALL be built from the subagent prompt parts

#### Scenario: Persona prompt is included as its own section
- **WHEN** a subagent started from a persona begins execution
- **THEN** its system prompt SHALL contain the persona's prompt as a delimited section in addition to the subagent prompt parts

#### Scenario: A session's own persona is included the same way
- **WHEN** a top-level job runs on a session that has adopted a persona
- **THEN** its system prompt SHALL contain that persona's prompt as a delimited section in addition to the base prompt parts

#### Scenario: A persona prompt cannot grant a tool
- **WHEN** a persona's prompt instructs the model to use a tool that the persona's allowlist excluded, or to spawn a subagent
- **THEN** the tool SHALL NOT be available to the job, because tools are computed from configuration rather than read from prompt text
