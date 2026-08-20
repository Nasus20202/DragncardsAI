ALTER TABLE evaluation_requests ADD COLUMN platform VARCHAR(32) NOT NULL DEFAULT 'dragncards';
ALTER TABLE evaluated_targets ADD COLUMN platform VARCHAR(32) NOT NULL DEFAULT 'dragncards';
ALTER TABLE evaluated_targets DROP CONSTRAINT uq_targets_game_seq_scope_player;
ALTER TABLE evaluated_targets ADD CONSTRAINT uq_targets_game_seq_scope_player UNIQUE (game_id, platform, target_seq, scope, player);
DROP INDEX ix_evaluation_requests_game_id;
DROP INDEX ix_evaluated_targets_game_id;
CREATE INDEX ix_evaluation_requests_game_id ON evaluation_requests (game_id, platform);
CREATE INDEX ix_evaluated_targets_game_id ON evaluated_targets (game_id, platform);
