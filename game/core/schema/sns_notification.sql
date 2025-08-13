CREATE TABLE IF NOT EXISTS sns_notification (
    notification_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    actor_id            INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    post_id             INTEGER DEFAULT NULL REFERENCES sns_post(post_id) ON DELETE CASCADE,
    notification_type   TEXT NOT NULL CHECK (notification_type IN ('follow', 'like', 'reply', 'mention')),
    is_read             INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    created_at          INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sns_notification_user_status ON sns_notification(user_id, is_read);