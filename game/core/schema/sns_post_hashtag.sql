CREATE TABLE IF NOT EXISTS sns_post_hashtag (
    post_id INTEGER NOT NULL REFERENCES sns_post(post_id) ON DELETE CASCADE,
    hashtag TEXT NOT NULL,
    PRIMARY KEY (post_id, hashtag)
);                
CREATE INDEX IF NOT EXISTS idx_sns_post_hashtag_hashtag ON sns_post_hashtag(hashtag);