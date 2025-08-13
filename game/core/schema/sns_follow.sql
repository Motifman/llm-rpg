CREATE TABLE IF NOT EXISTS sns_follow (
    follower_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    following_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (follower_id, following_id)
);
CREATE INDEX IF NOT EXISTS idx_sns_follow_following_id ON sns_follow(following_id);
CREATE INDEX IF NOT EXISTS idx_sns_follow_follower_id ON sns_follow(follower_id);