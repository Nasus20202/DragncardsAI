-- Create global skill registry table
CREATE TABLE skill_registries (
    name TEXT PRIMARY KEY,
    skill_path TEXT NOT NULL,
    description TEXT,
    metadata_json JSON NOT NULL,
    created_at TEXT NOT NULL
);

-- Drop old per-session skill assignments table
DROP TABLE IF EXISTS session_skill_assignments;

-- Create session skill enablement table
CREATE TABLE session_enabled_skills (
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    skill_name TEXT NOT NULL REFERENCES skill_registries(name),
    enabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CONSTRAINT uq_session_skill_enabled UNIQUE (session_id, skill_name)
);