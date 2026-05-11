ALTER TABLE agent_sessions ADD COLUMN multi_turn_memory BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE jobs ADD COLUMN tokens_used INTEGER NOT NULL DEFAULT 0;

CREATE TABLE compaction_records (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    summary_text TEXT NOT NULL,
    covers_up_to_job_id VARCHAR(36) NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX ix_compaction_records_session_id ON compaction_records(session_id);
