ALTER TABLE evaluated_targets
    ADD COLUMN player VARCHAR(16) NOT NULL DEFAULT '';

ALTER TABLE evaluated_targets
    DROP CONSTRAINT uq_targets_game_seq_scope;

ALTER TABLE evaluated_targets
    ADD CONSTRAINT uq_targets_game_seq_scope_player
        UNIQUE (game_id, target_seq, scope, player);
