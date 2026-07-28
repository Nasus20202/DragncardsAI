-- Questions the agent asked the user, and the answers it waited for.
-- choices_json holds exactly the choices the model offered and is the authority
-- a submitted answer is validated against.
-- status is 'pending', 'answered', or 'closed'. Both transitions out of
-- 'pending' are applied conditionally on it, so only one caller can make each.
-- Keep semicolons out of these comments: the migration runner splits statements
-- on them.
CREATE TABLE job_questions (
    id TEXT NOT NULL PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    choices_json JSON NOT NULL,
    allow_free_text BOOLEAN NOT NULL,
    status TEXT NOT NULL,
    answer_source TEXT,
    answer_value TEXT,
    answer_label TEXT,
    answer_text TEXT,
    closed_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX ix_job_questions_job_id ON job_questions (job_id);

CREATE INDEX ix_job_questions_session_id ON job_questions (session_id);
