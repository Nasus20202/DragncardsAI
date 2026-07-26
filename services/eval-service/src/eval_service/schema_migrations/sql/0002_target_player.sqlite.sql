CREATE TABLE evaluated_targets_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id VARCHAR(64) NOT NULL REFERENCES evaluation_requests (request_id),
    game_id VARCHAR(64) NOT NULL,
    target_seq BIGINT NOT NULL,
    scope VARCHAR(16) NOT NULL,
    player VARCHAR(16) NOT NULL DEFAULT '',
    round_from_seq BIGINT,
    round_to_seq BIGINT,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    error TEXT,
    verdict_json JSON,
    judge_config_json JSON,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    CONSTRAINT uq_targets_game_seq_scope_player UNIQUE (game_id, target_seq, scope, player)
);

INSERT INTO evaluated_targets_new (
    id, request_id, game_id, target_seq, scope, player, round_from_seq,
    round_to_seq, status, error, verdict_json, judge_config_json, created_at,
    updated_at
)
SELECT
    id, request_id, game_id, target_seq, scope, '', round_from_seq,
    round_to_seq, status, error, verdict_json, judge_config_json, created_at,
    updated_at
FROM evaluated_targets;

DROP TABLE evaluated_targets;

ALTER TABLE evaluated_targets_new RENAME TO evaluated_targets;

CREATE INDEX ix_evaluated_targets_game_id ON evaluated_targets (game_id);

CREATE INDEX ix_evaluated_targets_request_id ON evaluated_targets (request_id);
