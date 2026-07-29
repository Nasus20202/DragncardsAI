-- Orchestrated mode, and the durable identity of a player seat.
-- See the PostgreSQL twin for why session_mode is a column and why
-- agent_session_id is deliberately not a foreign key.
-- Keep semicolons out of these comments: the migration runner splits statements
-- on them.
ALTER TABLE agent_sessions ADD COLUMN session_mode VARCHAR(16) NOT NULL DEFAULT 'chat';

ALTER TABLE session_player_configs ADD COLUMN persona VARCHAR(64);

ALTER TABLE session_player_configs ADD COLUMN agent_session_id VARCHAR(36);
