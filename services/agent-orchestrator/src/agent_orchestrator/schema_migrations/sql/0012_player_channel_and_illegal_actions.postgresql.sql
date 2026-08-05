-- The player-to-player channel, and the record of illegal actions.
--
-- Both tables hang off the ORCHESTRATING session rather than off a seat's own
-- session, and that is the whole reason session_id is shaped this way: a seat's
-- session is a separate agent_sessions row created the first time that seat
-- plays, so the sender and the recipient of a message share no id except the
-- orchestrating session they are both seats of. Keying on the orchestrating
-- session is therefore what makes "a configured seat of the same table" a
-- lookup rather than a guess, and it is also what scopes a finding to one game.
--
-- player_messages.delivered_at is NULL until the message reaches its recipient.
-- Delivery is pull, at the start of the recipient's next invocation, because a
-- player agent only exists while it is running a job -- there is nothing to push
-- to between rounds, and holding a message in process memory is forbidden. The
-- index covers exactly the undelivered lookup that delivery performs.
--
-- player_illegal_actions.status is 'open' or 'resolved'. Only the orchestrating
-- agent may resolve one, and only after verifying the undo against game state:
-- a seat's claim to have undone something is data to check, never the check. The
-- transition out of 'open' is applied conditionally on this column, so a double
-- resolve is a no-op rather than a second resolution. round_number is nullable
-- because the orchestrator may notice a violation without knowing which round of
-- play it belongs to.
--
-- Keep semicolons out of these comments: the migration runner splits statements
-- on them.
CREATE TABLE player_messages (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    sender_player_id VARCHAR(16) NOT NULL,
    recipient_player_id VARCHAR(16) NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    delivered_at TIMESTAMP
);

CREATE INDEX ix_player_messages_undelivered
    ON player_messages (session_id, recipient_player_id, delivered_at);

CREATE TABLE player_illegal_actions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    session_id VARCHAR(36) NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE,
    player_id VARCHAR(16) NOT NULL,
    round_number INTEGER,
    violation TEXT NOT NULL,
    required_undo TEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    resolution_note TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP
);

CREATE INDEX ix_player_illegal_actions_seat_status
    ON player_illegal_actions (session_id, player_id, status);
