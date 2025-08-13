CREATE TABLE IF NOT EXISTS sns_post_allowed_user (
    post_id INTEGER NOT NULL REFERENCES sns_post(post_id) ON DELETE CASCADE,
    allowed_user_id INTEGER NOT NULL REFERENCES sns_user(user_id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, allowed_user_id)
);