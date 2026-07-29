-- Orchestrated mode, and the durable identity of a player seat.
--
-- session_mode is a column rather than a metadata key for three reasons. It has
-- to be queryable, it has to have a default so every row that predates it reads
-- as 'chat', and it must not be settable through the free-form metadata blob a
-- client may write, because it decides whether seat scoping applies.
--
-- session_player_configs.persona names the seat's persona, resolved and
-- snapshotted when the seat's session is created. agent_session_id is the seat's
-- own persistent agent session, NULL until the seat is first prompted. It is
-- deliberately not a foreign key: terminating a seat's session must not cascade
-- into the seat's configuration, and the reverse direction is already covered by
-- the session_id foreign key.
--
-- Keep semicolons out of these comments: the migration runner splits statements
-- on them.
ALTER TABLE agent_sessions ADD COLUMN session_mode VARCHAR(16) NOT NULL DEFAULT 'chat';

ALTER TABLE session_player_configs ADD COLUMN persona VARCHAR(64);

ALTER TABLE session_player_configs ADD COLUMN agent_session_id VARCHAR(36);
