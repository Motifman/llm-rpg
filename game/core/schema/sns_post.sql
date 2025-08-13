CREATE TABLE IF NOT EXISTS sns_post (
    post_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    content   TEXT NOT NULL,
    parent_post_id INTEGER DEFAULT NULL REFERENCES sns_post(post_id) ON DELETE SET NULL,
    visibility TEXT NOT NULL DEFAULT 'public',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    CHECK (visibility IN ('public', 'followers_only', 'mutual_follows_only', 'specified_users', 'private'))
);
CREATE INDEX IF NOT EXISTS idx_sns_post_created_at ON sns_post(created_at);
CREATE INDEX IF NOT EXISTS idx_sns_post_user_created_at ON sns_post(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_sns_post_public_created_at ON sns_post(created_at) WHERE visibility = 'public';