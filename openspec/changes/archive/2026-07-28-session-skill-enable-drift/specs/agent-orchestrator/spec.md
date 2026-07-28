## MODIFIED Requirements

### Requirement: Skill assignment
The system SHALL allow clients to assign and remove skills from `@skills/` for an agent session, discovered from environment-configured skill roots using the directory shape `skills/<skill_name>`.

The system SHALL maintain a persistent registry of known skills in PostgreSQL. On startup it SHALL upsert every skill discovered in the configured skill roots into that registry, so the registry reflects what is on disk rather than only the skills some session has already enabled. The sync SHALL be idempotent and SHALL NOT delete registry rows for skills that are no longer on disk, because existing session assignments reference them.

Any skill that resolves in the configured skill roots SHALL be enablable for a session, whether or not it has been enabled before and whether or not it was present at startup. A request that enables a skill SHALL register it first when it is not already registered.

Disabling a skill for a session SHALL be idempotent: when the skill is already disabled, was never enabled, or cannot be resolved at all, the system SHALL report success without changing state, because the session is already in the requested state. A request that targets a session that does not exist SHALL still be rejected as not found.

A session's assigned skills SHALL be reported consistently across endpoints: the session summary, the session detail, and the session skill list SHALL each include only the skills currently enabled for that session, and SHALL NOT report a disabled skill as assigned.

#### Scenario: Assign known skill
- **WHEN** a client assigns a skill identifier that exists under `skills/<skill_name>` in a configured skill root
- **THEN** the system SHALL persist the skill assignment for the session

#### Scenario: Reject unknown skill
- **WHEN** a client assigns a skill identifier that cannot be resolved from configured skill roots
- **THEN** the system SHALL reject the assignment and SHALL NOT persist it

#### Scenario: On-disk skills are registered at startup
- **WHEN** the agent-orchestrator starts with skills present in its configured skill roots
- **THEN** it SHALL upsert a registry row for each discovered skill, recording its path and summary
- **AND** starting again SHALL leave the registry in the same state

#### Scenario: Enable a skill that has never been enabled before
- **WHEN** a client enables a skill that resolves in a configured skill root but has no registry row
- **THEN** the system SHALL register that skill and persist the assignment
- **AND** SHALL NOT reject the request as not found

#### Scenario: Disable a skill that is already disabled
- **WHEN** a client disables a skill that a session has already disabled, or has never enabled
- **THEN** the system SHALL report success and leave the session's skills unchanged

#### Scenario: Disable a skill on a session that does not exist
- **WHEN** a client disables a skill for an unknown session id
- **THEN** the system SHALL reject the request as not found

#### Scenario: A disabled skill is not reported as assigned
- **WHEN** a client disables a skill for a session and then reads that session
- **THEN** the session summary, the session detail, and the session skill list SHALL all omit that skill

### Requirement: System prompt construction uses skill summaries
The worker SHALL build the system prompt by including only a short skill summary for each assigned skill rather than the full `SKILL.md` content. Full skill content SHALL be delivered on demand through the built-in skill-loading tools.

Only skills currently enabled for the session SHALL be treated as assigned. A disabled skill SHALL NOT appear in the system prompt, SHALL NOT be loadable through the skill-loading built-ins, SHALL NOT be counted in the session's context-usage estimate, and SHALL NOT be inherited by a subagent or player agent.

#### Scenario: System prompt with assigned skills
- **WHEN** a job starts with skills assigned to the session
- **THEN** the system prompt SHALL contain an "Available skills" section listing each skill name and summary
- **THEN** the system prompt SHALL instruct the agent to call `load_skill` before using a skill and `load_skill_reference` only for the specific reference files it chooses to inspect
- **THEN** the system prompt SHALL NOT include the full body of any assigned `SKILL.md`

#### Scenario: System prompt with no assigned skills
- **WHEN** a job starts with no skills assigned
- **THEN** the system prompt SHALL contain the base identity and tool-usage instructions only

#### Scenario: Disabled skill withdrawn from the agent
- **WHEN** a job starts for a session that has one enabled skill and one disabled skill
- **THEN** the system prompt SHALL list only the enabled skill
- **AND** the disabled skill SHALL NOT be loadable through `load_skill`
