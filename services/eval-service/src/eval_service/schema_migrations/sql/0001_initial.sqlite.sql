CREATE TABLE evaluation_requests (
    request_id VARCHAR(64) PRIMARY KEY,
    game_id VARCHAR(64) NOT NULL,
    scope VARCHAR(16) NOT NULL,
    selection_json JSON NOT NULL,
    force INTEGER NOT NULL DEFAULT 0,
    judge_config_json JSON,
    created_at VARCHAR(40) NOT NULL
);

CREATE INDEX ix_evaluation_requests_game_id ON evaluation_requests (game_id);

CREATE TABLE evaluated_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id VARCHAR(64) NOT NULL REFERENCES evaluation_requests (request_id),
    game_id VARCHAR(64) NOT NULL,
    target_seq BIGINT NOT NULL,
    scope VARCHAR(16) NOT NULL,
    round_from_seq BIGINT,
    round_to_seq BIGINT,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    error TEXT,
    verdict_json JSON,
    judge_config_json JSON,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    CONSTRAINT uq_targets_game_seq_scope UNIQUE (game_id, target_seq, scope)
);

CREATE INDEX ix_evaluated_targets_game_id ON evaluated_targets (game_id);
CREATE INDEX ix_evaluated_targets_request_id ON evaluated_targets (request_id);
