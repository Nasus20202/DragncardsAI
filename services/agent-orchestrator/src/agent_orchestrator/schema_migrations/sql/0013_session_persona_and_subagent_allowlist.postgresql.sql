-- A persona for the session's own agent, and the allowlist of personas that
-- session's agent may start a subagent from.
--
-- agent_sessions.session_persona names the persona the session's OWN agent runs
-- as. It is a column rather than a metadata key for the same reason session_mode
-- is: it gates behaviour, and metadata_json is writable by any client through
-- PATCH /sessions. The resolved snapshot still lives under the agent_persona
-- metadata key, exactly as a spawned child's does, so one reader interprets both
-- and a persona edited later cannot retroactively change a session that already
-- adopted it. The router owns that key and refuses to take it from a client.
--
-- session_allowed_subagents is the per-session allowlist, shaped like
-- session_enabled_skills: one row per (session, persona), an enabled flag that is
-- a soft toggle rather than a delete, and a foreign key onto the deployment-global
-- catalogue the names come from. AN EMPTY ALLOWLIST MEANS NO PERSONA MAY BE
-- SPAWNED. It is never read as "every persona", because a control whose most
-- restrictive-looking state is its most permissive one cannot be reasoned about.
--
-- Existing sessions are backfilled with the whole persona catalogue so that no
-- session already in flight loses a capability it had before this migration ran.
-- New sessions start closed and the operator opens them, which is the only
-- default under which the empty state means what it says.
--
-- Keep semicolons out of these comments: the migration runner splits statements
-- on them.
ALTER TABLE agent_sessions ADD COLUMN session_persona VARCHAR(64);

CREATE TABLE session_allowed_subagents (
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    persona_name VARCHAR(64) NOT NULL REFERENCES agent_personas(name),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (session_id, persona_name)
);

INSERT INTO session_allowed_subagents (
    session_id, persona_name, enabled, created_at, updated_at
)
SELECT s.id, p.name, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM agent_sessions s
CROSS JOIN agent_personas p;
