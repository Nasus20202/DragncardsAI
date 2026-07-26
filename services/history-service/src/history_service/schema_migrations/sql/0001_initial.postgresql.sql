CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    seq BIGINT NOT NULL,
    envelope_version INTEGER NOT NULL,
    actor VARCHAR(32) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload_json JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    producer_offset VARCHAR(128),
    CONSTRAINT uq_events_game_idempotency UNIQUE (game_id, idempotency_key),
    CONSTRAINT uq_events_game_seq UNIQUE (game_id, seq)
);

CREATE INDEX ix_events_game_id ON events (game_id);
CREATE INDEX ix_events_game_seq ON events (game_id, seq);

CREATE TABLE snapshots (
    id BIGSERIAL PRIMARY KEY,
    game_id VARCHAR(64) NOT NULL,
    snapshot_at_seq BIGINT NOT NULL,
    snapshot_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_snapshots_game_seq UNIQUE (game_id, snapshot_at_seq)
);

CREATE INDEX ix_snapshots_game_id ON snapshots (game_id);
CREATE INDEX ix_snapshots_game_seq ON snapshots (game_id, snapshot_at_seq);
