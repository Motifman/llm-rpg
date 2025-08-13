CREATE TABLE IF NOT EXISTS sns_mention (
    mention_id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES sns_post(post_id) ON DELETE CASCADE,
    mentioner_user_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    mentioned_user_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sns_mention_mentioned_user_id ON sns_mention(mentioned_user_id);