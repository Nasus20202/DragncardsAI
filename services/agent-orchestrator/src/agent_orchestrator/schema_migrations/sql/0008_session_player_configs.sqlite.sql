-- Per-seat agent configuration for orchestrated multi-player games.
-- NULL provider_id / model_name / skills_json mean "inherit from the session".
CREATE TABLE session_player_configs (
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    player_id TEXT NOT NULL,
    display_name TEXT,
    provider_id TEXT,
    model_name TEXT,
    gateway_options JSON NOT NULL,
    provider_options JSON NOT NULL,
    skills_json JSON,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (session_id, player_id)
);
