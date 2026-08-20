CREATE TABLE events_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id VARCHAR(64) NOT NULL,
    game_id VARCHAR(64) NOT NULL,
    platform VARCHAR(32) NOT NULL DEFAULT 'dragncards',
    seq BIGINT NOT NULL,
    envelope_version INTEGER NOT NULL,
    actor VARCHAR(32) NOT NULL,
    event_type VARCHAR(128) NOT NULL,
    payload_json JSON NOT NULL,
    occurred_at VARCHAR(40) NOT NULL,
    recorded_at VARCHAR(40) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    producer_offset VARCHAR(128),
    CONSTRAINT uq_events_game_idempotency UNIQUE (game_id, platform, idempotency_key),
    CONSTRAINT uq_events_game_seq UNIQUE (game_id, platform, seq)
);
INSERT INTO events_new (id, event_id, game_id, platform, seq, envelope_version, actor, event_type, payload_json, occurred_at, recorded_at, idempotency_key, producer_offset)
SELECT id, event_id, game_id, 'dragncards', seq, envelope_version, actor, event_type, payload_json, occurred_at, recorded_at, idempotency_key, producer_offset FROM events;
DROP TABLE events;
ALTER TABLE events_new RENAME TO events;
CREATE INDEX ix_events_game_id ON events (game_id, platform);
CREATE INDEX ix_events_game_seq ON events (game_id, platform, seq);
CREATE TABLE snapshots_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id VARCHAR(64) NOT NULL,
    platform VARCHAR(32) NOT NULL DEFAULT 'dragncards',
    snapshot_at_seq BIGINT NOT NULL,
    snapshot_json JSON NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    CONSTRAINT uq_snapshots_game_seq UNIQUE (game_id, platform, snapshot_at_seq)
);
INSERT INTO snapshots_new (id, game_id, platform, snapshot_at_seq, snapshot_json, created_at)
SELECT id, game_id, 'dragncards', snapshot_at_seq, snapshot_json, created_at FROM snapshots;
DROP TABLE snapshots;
ALTER TABLE snapshots_new RENAME TO snapshots;
CREATE INDEX ix_snapshots_game_id ON snapshots (game_id, platform);
CREATE INDEX ix_snapshots_game_seq ON snapshots (game_id, platform, snapshot_at_seq);
