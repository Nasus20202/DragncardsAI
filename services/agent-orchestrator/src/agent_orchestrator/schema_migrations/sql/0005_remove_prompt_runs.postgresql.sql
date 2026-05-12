-- Add prompt and metadata columns directly to jobs
ALTER TABLE jobs ADD COLUMN prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE jobs ADD COLUMN metadata_json JSON NOT NULL DEFAULT '{}';

-- Copy prompt text and metadata from prompt_runs into jobs
UPDATE jobs
SET
    prompt = prompt_runs.prompt,
    metadata_json = prompt_runs.metadata_json
FROM prompt_runs
WHERE jobs.prompt_run_id = prompt_runs.id;

-- Drop the FK column (constraint is dropped automatically in PostgreSQL)
ALTER TABLE jobs DROP COLUMN prompt_run_id;

-- Drop tables that are no longer needed
DROP TABLE IF EXISTS job_attempts;
DROP TABLE IF EXISTS prompt_runs;
