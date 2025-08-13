CREATE TABLE IF NOT EXISTS sns_block (
    blocker_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    blocked_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (blocker_id, blocked_id)
);
CREATE INDEX IF NOT EXISTS idx_sns_block_blocked_id ON sns_block(blocked_id);