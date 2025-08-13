CREATE TABLE IF NOT EXISTS quest_reward_unique_item (
    quest_id INTEGER NOT NULL REFERENCES quest(quest_id) ON DELETE CASCADE,
    unique_item_id INTEGER NOT NULL REFERENCES unique_item(unique_item_id) ON DELETE CASCADE,
    PRIMARY KEY (quest_id, unique_item_id)
);
CREATE INDEX IF NOT EXISTS idx_quest_reward_unique_item_quest_id ON quest_reward_unique_item(quest_id);