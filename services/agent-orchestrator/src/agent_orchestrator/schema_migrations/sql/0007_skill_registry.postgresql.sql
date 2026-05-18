-- Create global skill registry table
CREATE TABLE skill_registries (
    name VARCHAR(255) PRIMARY KEY,
    skill_path TEXT NOT NULL,
    description TEXT,
    metadata_json JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);

-- Drop old per-session skill assignments table
DROP TABLE IF EXISTS session_skill_assignments;

-- Create session skill enablement table
CREATE TABLE session_enabled_skills (
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    skill_name VARCHAR(255) NOT NULL REFERENCES skill_registries(name),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_session_skill_enabled UNIQUE (session_id, skill_name)
);