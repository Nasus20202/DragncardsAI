-- Add prompt and metadata columns directly to jobs
ALTER TABLE jobs ADD COLUMN prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN metadata_json JSON NOT NULL DEFAULT '{}';

-- Copy prompt text and metadata from prompt_runs into jobs
UPDATE jobs
SET
    prompt = (SELECT prompt_runs.prompt FROM prompt_runs WHERE prompt_runs.id = jobs.prompt_run_id),
    metadata_json = (SELECT prompt_runs.metadata_json FROM prompt_runs WHERE prompt_runs.id = jobs.prompt_run_id);

-- Recreate jobs without prompt_run_id (SQLite cannot drop FK columns directly)
CREATE TABLE jobs_new (
    id VARCHAR(36) PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    job_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    error_code VARCHAR(64),
    error_message TEXT,
    result_text TEXT,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    parent_job_id VARCHAR(36) REFERENCES jobs_new(id) ON DELETE SET NULL,
    cancellation_requested_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    updated_at TIMESTAMP NOT NULL,
    prompt TEXT NOT NULL DEFAULT '',
    metadata_json JSON NOT NULL DEFAULT '{}'
);

INSERT INTO jobs_new (id, session_id, job_type, status, attempts, max_attempts, error_code, error_message, result_text, tokens_used, parent_job_id, cancellation_requested_at, created_at, started_at, completed_at, updated_at, prompt, metadata_json)
SELECT id, session_id, job_type, status, attempts, max_attempts, error_code, error_message, result_text, tokens_used, parent_job_id, cancellation_requested_at, created_at, started_at, completed_at, updated_at, prompt, metadata_json
FROM jobs;

DROP TABLE jobs;

ALTER TABLE jobs_new RENAME TO jobs;

-- Restore indexes
CREATE INDEX IF NOT EXISTS ix_job_events_job_id ON job_events(job_id);
CREATE INDEX IF NOT EXISTS ix_job_outputs_job_id ON job_outputs(job_id);

-- Drop tables that are no longer needed
DROP TABLE IF EXISTS job_attempts;
DROP TABLE IF EXISTS prompt_runs;
