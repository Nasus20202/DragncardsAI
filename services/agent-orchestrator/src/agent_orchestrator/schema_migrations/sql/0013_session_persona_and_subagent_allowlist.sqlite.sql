-- The SQLite dialect of 0013. See the PostgreSQL file for the reasoning behind
-- the column, the table shape, and the backfill.
--
-- Keep semicolons out of these comments: the migration runner splits statements
-- on them.
ALTER TABLE agent_sessions ADD COLUMN session_persona TEXT;

CREATE TABLE session_allowed_subagents (
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    persona_name TEXT NOT NULL REFERENCES agent_personas(name),
    enabled BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (session_id, persona_name)
);

INSERT INTO session_allowed_subagents (
    session_id, persona_name, enabled, created_at, updated_at
)
SELECT s.id, p.name, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM agent_sessions s
CROSS JOIN agent_personas p;
