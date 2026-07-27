-- Per-seat agent configuration for orchestrated multi-player games.
-- NULL provider_id / model_name / skills_json mean "inherit from the session".
CREATE TABLE session_player_configs (
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    player_id VARCHAR(16) NOT NULL,
    display_name VARCHAR(255),
    provider_id VARCHAR(64),
    model_name VARCHAR(255),
    gateway_options JSON NOT NULL,
    provider_options JSON NOT NULL,
    skills_json JSON,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    PRIMARY KEY (session_id, player_id)
);
